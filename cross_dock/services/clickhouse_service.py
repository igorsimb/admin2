"""Select the same supplier offers from live source data or the refreshed snapshot.

SLOW resolves source replacements with FINAL. FAST reads the last completed RMV
refresh. Both use current supplier metadata and identical eligibility and ranking.
Input brand aliases are normalized once by the report service before querying.
"""

from contextlib import contextmanager
from functools import partial

import pandas as pd

from common.utils.clickhouse import get_clickhouse_client

DAYS_LOOKBACK = 2
OFFER_COLUMNS = ["price", "quantity", "supplier_name"]
PAIR_COLUMNS = [*OFFER_COLUMNS, "brand", "sku"]


def _supplier_ids(client, supplier_list: str) -> tuple[int, ...]:
    result = client.query(
        "SELECT dif_id FROM sup_stat.sup_list FINAL WHERE has(lists, %(supplier_list)s)",
        parameters={"supplier_list": supplier_list},
    )
    return tuple(row[0] for row in result.result_rows)


@contextmanager
def supplier_query_session(supplier_list: str):
    """Resolve the supplier group once and reuse its connection for SLOW rows."""
    with get_clickhouse_client() as client:
        yield partial(_query_supplier_data, client, _supplier_ids(client, supplier_list))


def query_supplier_data(brand: str, sku: str, supplier_list: str, days_lookback: int = DAYS_LOOKBACK) -> pd.DataFrame:
    """Query one canonical brand/SKU pair from the source with FINAL."""
    with supplier_query_session(supplier_list) as query:
        return query(brand, sku, days_lookback=days_lookback)


def _query_supplier_data(
    client, supplier_ids: tuple[int, ...], brand: str, sku: str, days_lookback: int = DAYS_LOOKBACK
) -> pd.DataFrame:
    pairs = [(str(brand).strip().upper(), str(sku).strip().upper())]
    return _query_supplier_pairs(client, supplier_ids, pairs, days_lookback, use_mv=False)[OFFER_COLUMNS]


def query_supplier_data_mv(
    brand_sku_pairs: list[tuple[str, str]], supplier_list: str, days_lookback: int = DAYS_LOOKBACK
) -> pd.DataFrame:
    """Query up to three offers per canonical brand/SKU pair from the RMV snapshot."""
    if not brand_sku_pairs:
        return pd.DataFrame(columns=PAIR_COLUMNS)
    with get_clickhouse_client() as client:
        return _query_supplier_pairs(
            client, _supplier_ids(client, supplier_list), brand_sku_pairs, days_lookback, use_mv=True
        )


def _query_supplier_pairs(client, supplier_ids, brand_sku_pairs, days_lookback, *, use_mv: bool) -> pd.DataFrame:
    pairs = sorted({(str(brand).strip().upper(), str(sku).strip().upper()) for brand, sku in brand_sku_pairs})
    pairs = [(brand, sku) for brand, sku in pairs if brand and sku]
    if not supplier_ids or not pairs:
        return pd.DataFrame(columns=PAIR_COLUMNS)

    # Only the source changes; eligibility and ranking must stay identical in both modes.
    source = (
        "SELECT supid, brand, sku, price, quantity, update_date FROM sup_stat.rmv_cross_dock"
        if use_mv
        else "SELECT supid, b AS brand, a AS sku, p AS price, q AS quantity, dateupd AS update_date "
        "FROM sup_stat.dif_step_1 FINAL"
    )
    query = f"""
    WITH recent_prices AS (
        SELECT
            df.price, df.quantity, sl.name AS supplier_name, df.brand, df.sku, df.supid,
            row_number() OVER (
                PARTITION BY df.brand, df.sku, df.supid
                ORDER BY df.update_date DESC, df.price ASC, df.quantity DESC
            ) AS offer_rank
        FROM ({source}) AS df
        INNER JOIN (SELECT dif_id, name FROM sup_stat.sup_list FINAL) AS sl ON df.supid = sl.dif_id
        WHERE (df.brand, df.sku) IN %(brand_sku_pairs)s
          AND df.update_date >= now() - INTERVAL %(days_lookback)s DAY
          AND df.supid IN %(supplier_ids)s
          AND df.quantity > 0
    ), ranked_suppliers AS (
        SELECT price, quantity, supplier_name, brand, sku, supid,
            row_number() OVER (
                PARTITION BY brand, sku
                ORDER BY price ASC, supplier_name ASC, supid ASC
            ) AS supplier_rank
        FROM recent_prices
        WHERE offer_rank = 1
    )
    SELECT price, quantity, supplier_name, brand, sku
    FROM ranked_suppliers
    WHERE supplier_rank <= 3
    ORDER BY brand, sku, price ASC, supplier_name ASC, supid ASC
    """
    result = client.query(
        query,
        parameters={"brand_sku_pairs": pairs, "supplier_ids": supplier_ids, "days_lookback": days_lookback},
    )
    return pd.DataFrame(result.result_rows, columns=PAIR_COLUMNS)
