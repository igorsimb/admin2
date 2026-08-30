"""Handles all interactions with the ClickHouse database, including DDL and batch inserts."""

from uuid import UUID

from common.utils.clickhouse import get_clickhouse_client
from .types import OfferRow


def insert_offers(run_id: UUID, rows: list[OfferRow]) -> None:
    """
    Inserts a batch of OfferRow objects into the ClickHouse database.

    Args:
        run_id: The UUID for the current parser run.
        rows: A list of OfferRow Pydantic models to insert.
    """
    if not rows:
        return

    table_name = "dif.stparts_percentage"

    # Convert Pydantic models to a list of dictionaries
    # `is_analog` is converted from bool to int (0 or 1)
    data_to_insert = [
        {
            "run_id": run_id,
            "b": row.b,
            "a": row.a,
            "price": row.price,
            "quantity": row.quantity,
            "delivery": row.delivery,
            "provider": row.provider,
            "rating": row.rating,
            "name": row.name,
            "is_analog": int(row.is_analog),
        }
        for row in rows
    ]

    # Get the column names from the first dictionary
    column_names = list(data_to_insert[0].keys())

    with get_clickhouse_client(readonly=0) as client:
        client.insert(table_name, data_to_insert, column_names=column_names)
