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
DAYS_LOOKBACK = 2


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


def query_supplier_data(brand: str, sku: str, supplier_list: str, days_lookback: int = DAYS_LOOKBACK) -> pd.DataFrame:
    """
    Query ClickHouse for supplier data for a specific brand and SKU.

    Args:
        brand: Product brand
        sku: Product SKU (Stock Keeping Unit) - equivalent to article number in the database
        supplier_list: Supplier list to query (e.g., 'Группа для проценки ТРЕШКА', 'ОПТ-2')
        days_lookback: Number of days to look back for supplier data (default: DAYS_LOOKBACK)

    Returns:
        DataFrame with supplier data sorted by price (price, quantity, supplier_name)
        Limited to 3 suppliers maximum

    Raises:
        Exception: If there's an error executing the query
    """
    logger.info(
        f"Querying supplier data for {brand}/{sku} with supplier list {supplier_list}, days_lookback={days_lookback}"
    )

    host = getattr(settings, "CLICKHOUSE_HOST", DEFAULT_CLICKHOUSE_HOST)
    user = getattr(settings, "CLICKHOUSE_USER", DEFAULT_CLICKHOUSE_USER)
    logger.info(f"Using ClickHouse connection: host={host}, user={user}")

    empty_df = pd.DataFrame(columns=["price", "quantity", "supplier_name"])

    try:
        try:
            with get_clickhouse_client() as client:
                suppliers_query = """
                SELECT DISTINCT dif_id
                FROM sup_stat.sup_list
                WHERE has(lists, %(supplier_list)s)
                """
                logger.info(f"Executing suppliers query with supplier_list={supplier_list}")
                suppliers_result = client.execute(suppliers_query, {"supplier_list": supplier_list})
                logger.info(f"Found {len(suppliers_result)} suppliers for supplier list {supplier_list}")
        except Exception as e:
            logger.error(f"Error executing suppliers query: {e}")
            # Try a simpler query to test the connection
            try:
                with get_clickhouse_client() as client:
                    test_query = "SELECT 1"
                    test_result = client.execute(test_query)
                    logger.info(f"Test query result: {test_result}")
            except Exception as test_e:
                logger.error(f"Error executing test query: {test_e}")
            return empty_df

        if not suppliers_result:
            logger.warning(f"No suppliers found for supplier list {supplier_list}")
            return empty_df

        supplier_ids = [item[0] for item in suppliers_result]

        # Special handling for Hyundai/Kia brands which can appear under multiple names
        if brand.lower() in ["hyundai/kia/mobis", "hyundai/kia"]:
            brand_values = ["hyundai/kia", "hyundai/kia/mobis"]
        else:
            brand_values = [brand.lower()]

        # For a given brand, SKU, and supplier list, return up to 3 suppliers with the lowest prices,
        # using only their most recent offer, and only if the offer is recent and has positive quantity.
        price_query = """
        WITH recent_prices AS (
            SELECT DISTINCT
                df.p as price,
                df.q as quantity,
                sl.name as supplier_name,
                df.dateupd,
                ROW_NUMBER() OVER (PARTITION BY sl.name ORDER BY df.dateupd DESC) AS rn
            FROM
                sup_stat.dif_step_1 AS df
            INNER JOIN
                sup_stat.sup_list AS sl
            ON
                df.supid = sl.dif_id
            WHERE
                lower(df.a) = %(sku_lower)s
                AND lower(df.b) IN %(brand_values)s
                AND df.dateupd >= now() - interval %(days_lookback)s day
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
        LIMIT 3;
        """

        query_params = {
            "sku_lower": sku.lower(),
            "brand_values": brand_values,
            "supplier_ids": supplier_ids,
            "days_lookback": days_lookback,
        }

        try:
            with get_clickhouse_client() as client:
                logger.info(
                    f"Executing price query with params: sku={sku.lower()}, brands={brand_values}, supplier_count={len(supplier_ids)}, days_lookback={days_lookback}, limit=3"
                )
                result = client.execute(price_query, query_params)
                logger.info(f"Query executed successfully, got {len(result)} results")
        except Exception as e:
            logger.error(f"Error executing price query: {e}")
            logger.warning("Returning empty results due to query error")
            return empty_df

        if result:
            result_df = pd.DataFrame(result, columns=["price", "quantity", "supplier_name"])
            logger.info(f"Created DataFrame with {len(result_df)} rows")
            logger.info(f"First few results: \n{result_df.head()}")
        else:
            result_df = empty_df
            logger.warning(f"No results found for {brand}/{sku} with supplier list {supplier_list}")

        logger.info(f"Found {len(result_df)} supplier results for {brand}/{sku}")
        return result_df

    except Exception as e:
        logger.exception(f"Error querying supplier data: {e}")
        raise


def query_supplier_data_mv(
    brand_sku_pairs: list[tuple[str, str]], supplier_list: str, days_lookback: int = DAYS_LOOKBACK
) -> pd.DataFrame:
    """
    Query ClickHouse Materialized View for supplier data for a batch of (brand, sku) pairs.

    Args:
        brand_sku_pairs: List of (brand, sku) tuples (all lowercase, deduplicated)
        supplier_list: Supplier list to query
        days_lookback: Number of days to look back for supplier data (default: DAYS_LOOKBACK)

    Returns:
        DataFrame with columns: price, quantity, supplier_name, brand_lower, sku_lower
        Contains up to 3 suppliers per (brand, sku) pair, sorted by price
    """
    logger.info(
        f"[MV-BATCH] Querying supplier data for {len(brand_sku_pairs)} (brand, sku) pairs with supplier list {supplier_list}, days_lookback={days_lookback}"
    )
    empty_df = pd.DataFrame(columns=["price", "quantity", "supplier_name", "brand_lower", "sku_lower"])

    if not brand_sku_pairs:
        logger.warning("[MV-BATCH] No (brand, sku) pairs provided.")
        return empty_df

    # Prepare the IN clause parameter for ClickHouse
    # ClickHouse expects a list of tuples for (brand_lower, sku_lower)
    try:
        query = """
        WITH recent_per_supplier AS (
            SELECT
                price,
                quantity,
                supplier_name,
                brand_lower,
                sku_lower,
                ROW_NUMBER() OVER (
                    PARTITION BY brand_lower, sku_lower, supplier_name
                    ORDER BY update_date DESC
                ) AS rn
            FROM sup_stat.mv_cross_dock
            WHERE supplier_list = %(supplier_list)s
              AND (brand_lower, sku_lower) IN %(brand_sku_pairs)s
              AND update_date >= now() - interval %(days_lookback)s day
        )
        SELECT
            price,
            quantity,
            supplier_name,
            brand_lower,
            sku_lower
        FROM (
            SELECT
                price,
                quantity,
                supplier_name,
                brand_lower,
                sku_lower,
                ROW_NUMBER() OVER (
                    PARTITION BY brand_lower, sku_lower
                    ORDER BY price ASC
                ) AS rank
            FROM recent_per_supplier
            WHERE rn = 1
        )
        WHERE rank <= 3
        ORDER BY brand_lower, sku_lower, price ASC;
        """

        query_params = {
            "supplier_list": supplier_list,
            "brand_sku_pairs": brand_sku_pairs,
            "days_lookback": days_lookback,
        }

        with get_clickhouse_client() as client:
            logger.info(f"[MV-BATCH] Executing batch MV query for {len(brand_sku_pairs)} pairs.")
            result = client.execute(query, query_params)
            logger.info(f"[MV-BATCH] Query executed successfully, got {len(result)} results")

        if result:
            result_df = pd.DataFrame(result, columns=["price", "quantity", "supplier_name", "brand_lower", "sku_lower"])
            logger.info(f"[MV-BATCH] Created DataFrame with {len(result_df)} rows")
        else:
            result_df = empty_df
            logger.warning(f"[MV-BATCH] No results found for batch query with supplier list {supplier_list}")

        return result_df

    except Exception as e:
        logger.exception(f"[MV-BATCH] Error querying supplier data in batch: {e}")
        return empty_df
