"""
Centralized utility for interacting with the ClickHouse database.

This module provides a reusable context manager for establishing connections
to ClickHouse, ensuring that all parts of the application use a consistent
connection method. It centralizes error handling and resource management.
"""

import contextlib
import logging

from clickhouse_driver import Client
from django.conf import settings

logger = logging.getLogger(__name__)

# Default ClickHouse connection settings
# These are fallbacks and should ideally be configured in Django's settings.
DEFAULT_CLICKHOUSE_HOST = "localhost"
DEFAULT_CLICKHOUSE_USER = "default"
DEFAULT_CLICKHOUSE_PASSWORD = ""


@contextlib.contextmanager
def get_clickhouse_client(readonly: int = 1) -> Client:
    """
    Provides a managed ClickHouse client connection.

    This context manager handles the creation and teardown of the ClickHouse
    client, including fetching credentials from Django settings and ensuring
    the connection is always closed.

    Args:
        readonly (int, optional): Whether to open the connection in read-only mode (1) or not (0). Defaults to 1.

    Yields:
        Client: A configured and connected ClickHouse client instance.

    Raises:
        Exception: Propagates any exceptions that occur during database operations.

    Example:
        try:
            with get_clickhouse_client() as client:
                result = client.execute("SELECT 1")
        except Exception as e:
            logger.error(f"Database query failed: {e}")
    """
    host = getattr(settings, "CLICKHOUSE_HOST", DEFAULT_CLICKHOUSE_HOST)
    user = getattr(settings, "CLICKHOUSE_USER", DEFAULT_CLICKHOUSE_USER)
    password = getattr(settings, "CLICKHOUSE_PASSWORD", DEFAULT_CLICKHOUSE_PASSWORD)

    client = Client(host, user=user, password=password, settings={"readonly": readonly})
    logger.debug(f"Connecting to ClickHouse at {host}...")

    try:
        yield client
    except Exception as e:
        logger.error(f"An error occurred with ClickHouse operation: {e}")
        raise
    finally:
        client.disconnect()
        logger.debug("ClickHouse client disconnected.")
