from unittest.mock import MagicMock, patch
from uuid import uuid4

from parser.clickhouse_repo import insert_offers
from parser.types import OfferRow


def test_insert_offers_calls_clickhouse_client_correctly():
    """Verify that `insert_offers` formats data correctly and calls the client's insert method."""
    mock_client = MagicMock()
    # Patch the context manager
    with patch("parser.clickhouse_repo.get_clickhouse_client", return_value=mock_client) as mock_get_client:
        run_id = uuid4()
        rows = [
            OfferRow(
                b="BrandA",
                a="ART1",
                name="Part A",
                price=100.50,
                quantity=10,
                provider="WH1",
                rating=None,
                delivery=5,
                is_analog=False,
            ),
            OfferRow(
                b="BrandB",
                a="ART2",
                name="Part B",
                price=200.00,
                quantity=2,
                provider="WH2",
                rating=90.0,
                delivery=2,
                is_analog=True,
            ),
        ]

        insert_offers(run_id, rows)

        # Check that the client was retrieved with readonly=0
        mock_get_client.assert_called_once_with(readonly=0)

        # Check that the insert method was called
        mock_client.__enter__.return_value.insert.assert_called_once()

        # Check the data passed to the insert method
        call_args = mock_client.__enter__.return_value.insert.call_args
        table_name = call_args.args[0]
        inserted_data = call_args.args[1]
        column_names = call_args.kwargs["column_names"]

        assert table_name == "dif.stparts_percentage"
        assert len(inserted_data) == 2
        assert column_names == [
            "run_id",
            "b",
            "a",
            "price",
            "quantity",
            "delivery",
            "provider",
            "rating",
            "name",
            "is_analog",
        ]
        # Check data for the second row
        assert inserted_data[1]["run_id"] == run_id
        assert inserted_data[1]["b"] == "BrandB"
        assert inserted_data[1]["is_analog"] == 1  # Bool converted to int


def test_insert_offers_handles_empty_list():
    """Verify that `insert_offers` does not call the client if the row list is empty."""
    mock_client = MagicMock()
    with patch("parser.clickhouse_repo.get_clickhouse_client", return_value=mock_client):
        insert_offers(uuid4(), [])

        mock_client.__enter__.return_value.insert.assert_not_called()


def test_insert_offers_handles_nullable_fields():
    """Verify that None values for nullable fields are handled correctly."""
    mock_client = MagicMock()
    with patch("parser.clickhouse_repo.get_clickhouse_client", return_value=mock_client):
        run_id = uuid4()
        rows_with_nulls = [
            OfferRow(
                b="BrandC",
                a="ART3",
                name="Part C",
                price=300.00,
                quantity=None,  # Nullable field
                provider="WH3",
                rating=None,
                delivery=None,  # Nullable field
                is_analog=False,
            )
        ]

        insert_offers(run_id, rows_with_nulls)

        mock_client.__enter__.return_value.insert.assert_called_once()
        call_args = mock_client.__enter__.return_value.insert.call_args
        inserted_data = call_args.args[1]

        assert len(inserted_data) == 1
        assert inserted_data[0]["quantity"] is None
        assert inserted_data[0]["delivery"] is None
