"""
Management command to backfill supplier data from ClickHouse.
"""

from django.core.management.base import BaseCommand

from common.models import Supplier
from common.utils.clickhouse import get_clickhouse_client


class Command(BaseCommand):
    help = "Backfills supplier data from ClickHouse into the Postgres Supplier model."

    def handle(self, *args, **options):
        self.stdout.write("Starting supplier backfill process...")

        try:
            with get_clickhouse_client() as client:
                if client is None:
                    self.stdout.write(self.style.ERROR("Failed to get ClickHouse client."))
                    return

                self.stdout.write("Fetching suppliers from ClickHouse sup_stat.sup_list...")
                query = "SELECT dif_id, name FROM sup_stat.sup_list"
                suppliers_from_ch = client.execute(query)

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"An error occurred with ClickHouse operation: {e}"))
            return

        if not suppliers_from_ch:
            self.stdout.write(self.style.WARNING("No suppliers found in ClickHouse. Aborting."))
            return

        self.stdout.write(f"Found {len(suppliers_from_ch)} suppliers in ClickHouse.")

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

        self.stdout.write(
            self.style.SUCCESS(f"Supplier backfill complete. Created: {created_count}, Updated: {updated_count}.")
        )
