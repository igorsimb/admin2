"""
Service for interacting with ClickHouse database.

This module provides functions for connecting to ClickHouse and executing queries.
It implements a context manager pattern for proper resource management and
includes error handling with detailed logging.
"""

import contextlib
import logging

import pandas as pd
from clickhouse_driver import Client
from django.conf import settings

logger = logging.getLogger(__name__)

# Default ClickHouse connection settings
# These will only be used if Django settings are not available
# In production, these values should always come from Django settings
DEFAULT_CLICKHOUSE_HOST = "localhost"
DEFAULT_CLICKHOUSE_USER = "default"
DEFAULT_CLICKHOUSE_PASSWORD = ""


@contextlib.contextmanager
def get_clickhouse_client() -> Client:
    """
    Context manager for ClickHouse client connections.

    Ensures proper resource management by automatically closing the connection
    when the context is exited, even if an exception occurs.

    Yields:
        Client: A configured ClickHouse client instance

    Example:
        with get_clickhouse_client() as client:
            result = client.execute("SELECT 1")
    """
    # Get connection settings from Django settings if available, otherwise use defaults
    host = getattr(settings, "CLICKHOUSE_HOST", DEFAULT_CLICKHOUSE_HOST)
    user = getattr(settings, "CLICKHOUSE_USER", DEFAULT_CLICKHOUSE_USER)
    password = getattr(settings, "CLICKHOUSE_PASSWORD", DEFAULT_CLICKHOUSE_PASSWORD)

    client = Client(host, user=user, password=password)
    logger.debug(f"ClickHouse client connected to {host}")

    try:
        yield client
    except Exception as e:
        logger.error(f"Error during ClickHouse operation: {e}")
        raise
    finally:
        client.disconnect()
        logger.debug("ClickHouse client disconnected")


def query_supplier_data(brand: str, sku: str, platform: str, limit: int = 3) -> pd.DataFrame:
    """
    Query ClickHouse for supplier data for a specific brand and SKU.

    Args:
        brand: Product brand
        sku: Product SKU (Stock Keeping Unit) - equivalent to article number in the database
        platform: Platform to query (e.g., 'emex', 'autopiter')
        limit: Maximum number of suppliers to return (default: 3)

    Returns:
        DataFrame with supplier data sorted by price (price, quantity, supplier_name)

    Raises:
        Exception: If there's an error executing the query
    """
    logger.info(f"Querying supplier data for {brand}/{sku} on platform {platform}")

    try:
        with get_clickhouse_client() as client:
            # First, get the list of suppliers for the platform
            suppliers_query = """
            SELECT DISTINCT dif_id
            FROM sup_stat.sup_list
            WHERE has(lists, %(platform)s)
            """
            suppliers_result = client.execute(suppliers_query, {'platform': platform})

            if not suppliers_result:
                logger.warning(f"No suppliers found for platform {platform}")
                return pd.DataFrame(columns=["price", "quantity", "supplier_name"])

            # Get supplier IDs as a list
            supplier_ids = [item[0] for item in suppliers_result]

            # Special handling for Hyundai/Kia brands
            if brand.lower() in ["hyundai/kia/mobis", "hyundai/kia"]:
                brand_values = ['hyundai/kia', 'hyundai/kia/mobis']
            else:
                brand_values = [brand.lower()]

            # Query for price data using the same logic as the original query
            price_query = """
            WITH recent_prices AS (
                SELECT DISTINCT
                    df.p as price,
                    df.q as quantity,
                    sl.name as supplier_name,
                    df.dateupd,
                    ROW_NUMBER() OVER (PARTITION BY sl.name ORDER BY df.dateupd DESC) AS rn
                FROM
                    dif.dif_step_1 AS df
                INNER JOIN
                    sup_stat.sup_list AS sl
                ON
                    df.supid = sl.dif_id
                WHERE
                    lower(df.a) = %(sku_lower)s
                    AND lower(df.b) IN %(brand_values)s
                    AND df.dateupd >= now() - interval 2 day
                    AND df.supid IN %(supplier_ids)s
                    AND df.q > 0
            ),
            ranked_suppliers AS (
                SELECT DISTINCT
                    price,
                    quantity,
                    supplier_name,
                    ROW_NUMBER() OVER (PARTITION BY supplier_name ORDER BY price ASC) AS rank
                FROM recent_prices
                WHERE rn = 1
            )
            SELECT
                price,
                quantity,
                supplier_name
            FROM
                ranked_suppliers
            WHERE
                rank = 1
            ORDER BY
                price ASC
            LIMIT %(limit)s;
            """

            # Prepare parameters for the query
            query_params = {
                'sku_lower': sku.lower(),
                'brand_values': brand_values,
                'supplier_ids': supplier_ids,
                'limit': limit
            }

            # Execute the query and convert to DataFrame
            result = client.execute(price_query, query_params)

            # Create DataFrame from results
            if result:
                result_df = pd.DataFrame(result, columns=["price", "quantity", "supplier_name"])
            else:
                result_df = pd.DataFrame(columns=["price", "quantity", "supplier_name"])

            logger.info(f"Found {len(result_df)} supplier results for {brand}/{sku}")
            return result_df

    except Exception as e:
        logger.exception(f"Error querying supplier data: {e}")
        raise
