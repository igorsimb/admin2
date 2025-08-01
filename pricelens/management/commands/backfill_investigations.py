from django.core.management.base import BaseCommand
from django.db import transaction

from common.models import Supplier
from common.utils.clickhouse import get_clickhouse_client
from pricelens.models import Investigation


class Command(BaseCommand):
    help = "One-time backfill of historical errors from ClickHouse into the Pricelens Investigation table."

    def handle(self, *args, **options):
        self.stdout.write("Starting backfill from ClickHouse...")

        # Get all existing supplier IDs from the database
        supplier_ids = list(Supplier.objects.values_list("supid", flat=True))
        if not supplier_ids:
            self.stderr.write(self.style.ERROR("No suppliers found in the database. Aborting."))
            return

        try:
            with get_clickhouse_client() as client:
                if client is None:
                    self.stderr.write(self.style.ERROR("Failed to get ClickHouse client. Aborting."))
                    return

                self.stdout.write("Executing ClickHouse query to fetch all historical errors...")
                # This query is from the blueprint, but modified to fetch ALL historical data
                # by removing the time constraint.
                query = """
                    SELECT e.dt AS event_dt, e.supid, e.error_id,
                           d.error_text,
                           'consolidate' AS stage
                    FROM sup_stat.dif_errors e
                    LEFT JOIN sup_stat.error_list d ON d.id = e.error_id
                    WHERE e.supid IN %(supids)s
                """
                params = {"supids": supplier_ids}
                rows = client.query_dataframe(query, params=params)
                self.stdout.write(f"Found {len(rows)} total error records in ClickHouse.")

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"An error occurred while querying ClickHouse: {e}"))
            return

        if rows.empty:
            self.stdout.write(self.style.SUCCESS("No error records found in ClickHouse. Nothing to backfill."))
            return

        # Convert timezone-naive datetimes from ClickHouse to timezone-aware
        rows["event_dt"] = rows["event_dt"].dt.tz_localize("Europe/Moscow")

        self.stdout.write("Fetching existing investigation records from PostgreSQL to prevent duplicates...")

        # Create a unique identifier for comparison
        rows["unique_key"] = rows.apply(lambda r: (r["event_dt"], r["supid"], r["error_id"]), axis=1)

        existing_keys = set(Investigation.objects.values_list("event_dt", "supplier_id", "error_id"))

        self.stdout.write(f"Found {len(existing_keys)} existing records in PostgreSQL.")

        new_rows = rows[~rows["unique_key"].isin(existing_keys)]

        if new_rows.empty:
            self.stdout.write(self.style.SUCCESS("No new records to add. PostgreSQL is already up-to-date."))
            return

        self.stdout.write(f"Preparing to insert {len(new_rows)} new investigation records...")

        new_investigations = []
        for _, row in new_rows.iterrows():
            new_investigations.append(
                Investigation(
                    event_dt=row["event_dt"],
                    supplier_id=row["supid"],
                    error_id=row["error_id"],
                    error_text=row["error_text"] or "Unknown Error",
                    stage=row["stage"],
                    file_path="",  # Backfilled events don't have a file path
                )
            )

        try:
            with transaction.atomic():
                Investigation.objects.bulk_create(new_investigations, batch_size=1000)
            self.stdout.write(self.style.SUCCESS(f"Successfully inserted {len(new_investigations)} new records."))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"An error occurred during bulk insert: {e}"))
