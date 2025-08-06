"""
Celery tasks for the Pricelens application.

This module contains the asynchronous tasks that handle periodic data synchronization
and analysis for the Pricelens feature. These tasks are scheduled to run automatically
by Celery Beat.
"""

import logging
from celery import shared_task
from django.db import transaction

from common.models import Supplier
from common.utils.clickhouse import get_clickhouse_client
from pricelens.models import CadenceProfile, Investigation, FailReason

logger = logging.getLogger(__name__)


@shared_task
def backfill_suppliers_task():
    """
    Celery task to periodically backfill supplier data from ClickHouse.

    This task ensures that the Postgres `Supplier` model stays synchronized
    with the `sup_stat.sup_list` table in ClickHouse.
    """
    logger.info("Starting supplier backfill task...")

    try:
        with get_clickhouse_client() as client:
            if client is None:
                logger.error("Failed to get ClickHouse client.")
                return

            logger.info("Fetching suppliers from ClickHouse sup_stat.sup_list...")
            query = "SELECT dif_id, name FROM sup_stat.sup_list"
            suppliers_from_ch = client.execute(query)

    except Exception as e:
        logger.error(f"An error occurred with ClickHouse operation: {e}")
        return

    if not suppliers_from_ch:
        logger.warning("No suppliers found in ClickHouse. Aborting.")
        return

    logger.info(f"Found {len(suppliers_from_ch)} suppliers in ClickHouse.")

    updated_count = 0
    created_count = 0
    for supid, name in suppliers_from_ch:
        _, created = Supplier.objects.update_or_create(
            supid=supid,
            defaults={"name": name if name else f"Supplier {supid}"},
        )
        if created:
            created_count += 1
        else:
            updated_count += 1

    logger.info(f"Supplier backfill complete. Created: {created_count}, Updated: {updated_count}.")


@shared_task
def refresh_cadence_profiles_task():
    """
    Celery task to refresh supplier cadence profiles from ClickHouse.

    This task runs the main cadence analysis query, calculates the bucket for each
    supplier (consistent, inconsistent, or dead), and updates the `CadenceProfile`
    table in Postgres.
    """
    logger.info("Starting cadence profile refresh task...")

    supplier_ids = list(Supplier.objects.values_list("supid", flat=True))
    if not supplier_ids:
        logger.error("No suppliers found in the database. Aborting cadence refresh.")
        return

    create_view_sql = """
        CREATE OR REPLACE VIEW sup_stat.success_days_180 AS
        SELECT
            supid,
            dateupd AS d
        FROM sup_stat.dif_step_1
        WHERE dateupd >= today() - 180 AND supid IN %(supids)s
        GROUP BY supid, d;
    """

    cadence_profile_sql = """
        WITH by_sup AS
        (
            SELECT
                supid,
                arraySort(groupArray(d)) AS days
            FROM sup_stat.success_days_180
            GROUP BY supid
        ),
        stats AS
        (
            SELECT
                supid,
                arrayFilter(x -> x > 0, arrayDifference(arrayMap(d -> toUInt32(d), days))) AS gaps,
                arrayReduce('quantileExact(0.5)', gaps) AS med_gap,
                arrayReduce('stddevPop', gaps)          AS sd_gap,
                dateDiff('day', arrayMax(days), today()) AS days_since_last,
                arrayMax(days)                           AS last_success_date,
                length(gaps)                             AS total_gaps,
                arrayCount(x -> x > med_gap * 2, gaps)   AS bad_gaps
            FROM by_sup
        )
        SELECT *
        FROM stats
        WHERE length(gaps) >= 1;   -- skip suppliers with <2 successes
    """
    params = {"supids": supplier_ids}

    try:
        with get_clickhouse_client(readonly=0) as client:
            if client is None:
                logger.error("Failed to get ClickHouse client. Aborting cadence refresh.")
                return

            logger.info("Ensuring the `success_days_180` view exists in ClickHouse...")
            client.execute(create_view_sql, params=params)
            logger.info("View is ready.")

            logger.info("Executing cadence profile query...")
            rows = client.query_dataframe(cadence_profile_sql)
            logger.info(f"Found {len(rows)} suppliers with sufficient data for cadence profiling.")

    except Exception as e:
        logger.error(f"An error occurred while querying ClickHouse: {e}")
        return

    if rows.empty:
        logger.info("No supplier profiles to update.")
        return

    logger.info(f"Updating {len(rows)} profiles in PostgreSQL...")

    updated_count = 0
    created_count = 0

    # --- Tuning Parameters ---
    CONSISTENCY_MULTIPLIER: float = 1.0
    BAD_GAP_PERCENTAGE_THRESHOLD: float = 20.0

    for _, row in rows.iterrows():
        if row["med_gap"] is None or row["sd_gap"] is None or row["med_gap"] == 0:
            continue

        days_since_last = row["days_since_last"]
        sd_gap = row["sd_gap"]
        med_gap = row["med_gap"]

        if days_since_last >= 28:
            bucket = "dead"
        else:
            is_consistent_by_std_dev = sd_gap <= med_gap * CONSISTENCY_MULTIPLIER
            total_gaps = row["total_gaps"]
            bad_gaps = row["bad_gaps"]
            bad_gap_percentage = (bad_gaps / total_gaps) * 100 if total_gaps > 0 else 0
            is_consistent_by_outliers = bad_gap_percentage < BAD_GAP_PERCENTAGE_THRESHOLD
            bucket = "consistent" if is_consistent_by_std_dev or is_consistent_by_outliers else "inconsistent"

        profile_data = {
            "median_gap_days": round(med_gap),
            "sd_gap": float(sd_gap),
            "days_since_last": days_since_last,
            "last_success_date": row["last_success_date"],
            "bucket": bucket,
        }

        _, created = CadenceProfile.objects.update_or_create(
            supplier_id=row["supid"],
            defaults=profile_data,
        )
        if created:
            created_count += 1
        else:
            updated_count += 1

    logger.info(f"Cadence profile refresh complete. Created: {created_count}, Updated: {updated_count}.")


@shared_task
def backfill_investigations_task():
    """
    Celery task to backfill historical errors from ClickHouse.

    This task acts as a safety net to ensure that any error events that were
    not captured by the real-time API are still logged as investigations.
    It is idempotent and safe to run multiple times.
    """
    logger.info("Starting backfill from ClickHouse...")

    supplier_ids = list(Supplier.objects.values_list("supid", flat=True))
    if not supplier_ids:
        logger.error("No suppliers found in the database. Aborting backfill.")
        return

    try:
        with get_clickhouse_client() as client:
            if client is None:
                logger.error("Failed to get ClickHouse client. Aborting backfill.")
                return

            logger.info("Executing ClickHouse query to fetch all historical errors...")
            query = """
                SELECT e.dt AS event_dt, e.supid, d.error_text
                FROM sup_stat.dif_errors e
                LEFT JOIN sup_stat.error_list d ON d.id = e.error_id
                WHERE e.supid IN %(supids)s AND d.error_text IS NOT NULL
            """
            params = {"supids": supplier_ids}
            rows = client.query_dataframe(query, params=params)
            logger.info(f"Found {len(rows)} total error records in ClickHouse.")

    except Exception as e:
        logger.error(f"An error occurred while querying ClickHouse: {e}")
        return

    if rows.empty:
        logger.info("No error records found in ClickHouse. Nothing to backfill.")
        return

    rows["event_dt"] = rows["event_dt"].dt.tz_localize("Europe/Moscow")

    unique_error_texts = rows["error_text"].unique()
    reasons_by_code = {}
    for code in unique_error_texts:
        reason, _ = FailReason.objects.get_or_create(code=code, defaults={"name": code, "description": ""})
        reasons_by_code[code] = reason

    rows["fail_reason_id"] = rows["error_text"].apply(lambda code: reasons_by_code[code].id)

    logger.info("Fetching existing investigation records from PostgreSQL to prevent duplicates...")
    rows["unique_key"] = rows.apply(lambda r: (r["event_dt"], r["supid"], r["fail_reason_id"]), axis=1)
    existing_keys = set(Investigation.objects.values_list("event_dt", "supplier_id", "fail_reason_id"))
    logger.info(f"Found {len(existing_keys)} existing records in PostgreSQL.")

    new_rows = rows[~rows["unique_key"].isin(existing_keys)]

    if new_rows.empty:
        logger.info("No new records to add. PostgreSQL is already up-to-date.")
        return

    logger.info(f"Preparing to insert {len(new_rows)} new investigation records...")

    new_investigations = [
        Investigation(
            event_dt=row["event_dt"],
            supplier_id=row["supid"],
            fail_reason_id=row["fail_reason_id"],
            stage="consolidate",
            file_path="",
        )
        for _, row in new_rows.iterrows()
    ]

    try:
        with transaction.atomic():
            Investigation.objects.bulk_create(new_investigations, batch_size=1000)
        logger.info(f"Successfully inserted {len(new_investigations)} new records.")
    except Exception as e:
        logger.error(f"An error occurred during bulk insert: {e}")
