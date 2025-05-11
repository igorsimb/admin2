"""
Tests for ClickHouse service.

This module contains tests for the ClickHouse service functions that will be used
for querying supplier data from ClickHouse.
"""

from unittest import mock

import pandas as pd
import pytest

from cross_dock.services.clickhouse_service import query_supplier_data


class TestClickHouseService:
    """Test suite for ClickHouse service functions."""

    @mock.patch('cross_dock.services.clickhouse_service.get_clickhouse_client')
    def test_query_supplier_data(self, mock_get_client):
        """Test that query_supplier_data correctly queries ClickHouse."""
        mock_client = mock.MagicMock()
        mock_get_client.return_value.__enter__.return_value = mock_client

        # Setup mock to return suppliers list and then price data
        mock_client.execute.side_effect = [
            [(1001,), (1002,), (1003,)],  # Suppliers query result
            [
                (100.50, 5, "Supplier A"),
                (120.75, 10, "Supplier B"),
                (90.25, 3, "Supplier C")
            ]  # Price query result
        ]

        result = query_supplier_data("HYUNDAI/KIA/MOBIS", "223112e100", "emex")

        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["price", "quantity", "supplier_name"]
        assert len(result) == 3
        assert result.iloc[0]["price"] == 100.50
        assert result.iloc[0]["quantity"] == 5
        assert result.iloc[0]["supplier_name"] == "Supplier A"

    @mock.patch('cross_dock.services.clickhouse_service.get_clickhouse_client')
    def test_query_supplier_data_no_suppliers(self, mock_get_client):
        """Test handling of no suppliers found."""
        mock_client = mock.MagicMock()
        mock_get_client.return_value.__enter__.return_value = mock_client
        mock_client.execute.return_value = []

        result = query_supplier_data("BRAND", "ARTICLE", "emex")

        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["price", "quantity", "supplier_name"]
        assert len(result) == 0

    @mock.patch('cross_dock.services.clickhouse_service.get_clickhouse_client')
    def test_query_supplier_data_exception(self, mock_get_client):
        """Test error handling in query_supplier_data."""
        mock_client = mock.MagicMock()
        mock_get_client.return_value.__enter__.return_value = mock_client
        mock_client.execute.side_effect = Exception("Test exception")

        # Instead of expecting an exception, check for empty DataFrame
        result = query_supplier_data("BRAND", "ARTICLE", "emex")
        
        # Verify the result is an empty DataFrame with the expected columns
        assert isinstance(result, pd.DataFrame)
        assert result.empty
        assert list(result.columns) == ["price", "quantity", "supplier_name"]
