"""
Management command to test ClickHouse connection.
"""

import logging

from django.core.management.base import BaseCommand

from cross_dock.services.clickhouse_service import get_clickhouse_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Test connection to ClickHouse database"

    def handle(self, *args, **options):
        self.stdout.write("Testing ClickHouse connection...")

        try:
            with get_clickhouse_client() as client:
                result = client.execute("SELECT 1")
                self.stdout.write(self.style.SUCCESS(f"Connection successful! Result: {result}"))

                # Get server version
                version = client.execute("SELECT version()")
                self.stdout.write(self.style.SUCCESS(f"ClickHouse version: {version[0][0]}"))

                return "Connection test completed successfully"
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Connection failed: {e}"))
            return f"Connection test failed: {e}"


# For direct script execution
def test_connection():
    logger.info("Testing ClickHouse connection...")

    try:
        with get_clickhouse_client() as client:
            result = client.execute("SELECT 1")
            logger.info(f"Connection successful! Result: {result}")

            version = client.execute("SELECT version()")
            logger.info(f"ClickHouse version: {version[0][0]}")

            return True
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        return False


if __name__ == "__main__":
    test_connection()
