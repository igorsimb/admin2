from django.core.management.base import BaseCommand

from common.models import Supplier
from common.utils.clickhouse import get_clickhouse_client
from pricelens.models import CadenceProfile

# --- Tuning Parameters ---
# Defines how much the standard deviation can be relative to the median gap.
# A value of 1.0 means the std dev can be up to the size of the median gap.
CONSISTENCY_MULTIPLIER: float = 1.0
# The percentage of "bad gaps" allowed before a supplier is flagged as inconsistent.
# A "bad gap" is a gap > median_gap * 2.
BAD_GAP_PERCENTAGE_THRESHOLD: float = 20.0


class Command(BaseCommand):
    """
    Refreshes supplier cadence profiles from ClickHouse.

    This command mirrors the logic in the Celery task `pricelens.tasks.refresh_cadence_profiles_task`.
    It is intended for manual execution to refresh the cadence data on demand, outside of the
    regularly scheduled Celery task.

    Usage:
        python manage.py refresh_cadence
    """
    help = "Refreshes supplier cadence profiles from ClickHouse."

    def handle(self, *args, **options):
        self.stdout.write("Starting cadence profile refresh from ClickHouse...")

        supplier_ids = list(Supplier.objects.values_list("supid", flat=True))
        if not supplier_ids:
            self.stderr.write(self.style.ERROR("No suppliers found in the database. Aborting."))
            return

        # SQL queries from the blueprint
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
                    self.stderr.write(self.style.ERROR("Failed to get ClickHouse client. Aborting."))
                    return

                self.stdout.write("Ensuring the `success_days_180` view exists in ClickHouse...")
                client.execute(create_view_sql, params=params)
                self.stdout.write(self.style.SUCCESS("View is ready."))

                self.stdout.write("Executing cadence profile query...")
                rows = client.query_dataframe(cadence_profile_sql)
                self.stdout.write(f"Found {len(rows)} suppliers with sufficient data for cadence profiling.")

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"An error occurred while querying ClickHouse: {e}"))
            return

        if rows.empty:
            self.stdout.write(self.style.SUCCESS("No supplier profiles to update."))
            return

        self.stdout.write(f"Updating {len(rows)} profiles in PostgreSQL...")

        updated_count = 0
        created_count = 0

        for _, row in rows.iterrows():
            # Basic validation from blueprint
            if row["med_gap"] is None or row["sd_gap"] is None or row["med_gap"] == 0:
                continue

            days_since_last = row["days_since_last"]
            sd_gap = row["sd_gap"]
            med_gap = row["med_gap"]

            # Determine bucket based on the hybrid logic
            if days_since_last >= 28:
                bucket = "dead"
            else:
                # Hybrid consistency check
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

        self.stdout.write(
            self.style.SUCCESS(f"Cadence profile refresh complete. Created: {created_count}, Updated: {updated_count}.")
        )
