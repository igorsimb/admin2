"""
Tests for Excel service.

This module contains tests for the Excel service functions that will be used
for processing cross-dock data and generating Excel files.
"""

import os
import tempfile
from unittest import mock

import pandas as pd
import pytest
from openpyxl import load_workbook

# Import will fail until we implement the code
from cross_dock.services.excel_service import process_cross_dock_data


class TestExcelService:
    """Test suite for Excel service functions."""

    @mock.patch('cross_dock.services.excel_service.query_supplier_data')
    def test_process_cross_dock_data(self, mock_query_supplier_data):
        """Test processing cross-dock data and generating an Excel file."""
        # Mock the query_supplier_data function
        mock_query_supplier_data.return_value = pd.DataFrame({
            "price": [100.50, 120.75, 90.25],
            "quantity": [5, 10, 3],
            "supplier_name": ["Supplier A", "Supplier B", "Supplier C"]
        })

        # Test data
        test_data = [
            {"Бренд": "HYUNDAI/KIA/MOBIS", "Артикул": "223112e100"},
            {"Бренд": "VAG", "Артикул": "000915105cd"}
        ]

        # Create a temporary directory for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock settings to use the temp directory
            with mock.patch('django.conf.settings.MEDIA_ROOT', temp_dir):
                with mock.patch('django.conf.settings.MEDIA_URL', '/media/'):
                    # Process the data
                    progress, file_url = process_cross_dock_data(test_data, "emex")

                    # Check the progress
                    assert progress == "100%"

                    # Check that the file exists
                    file_path = os.path.join(temp_dir, 'exports', os.path.basename(file_url))
                    assert os.path.exists(file_path)

                    # Load the workbook and check its contents
                    wb = load_workbook(file_path)
                    sheet = wb.active

                    # Check headers
                    headers = ["SKU", "Бренд", "Артикул", "Лучшая цена 1", "Количество 1", "Название поставщика 1",
                            "Лучшая цена 2", "Количество 2", "Название поставщика 2",
                            "Лучшая цена 3", "Количество 3", "Название поставщика 3"]
                    for col_num, header in enumerate(headers, start=1):
                        assert sheet.cell(row=1, column=col_num).value == header

                    # Check first row data
                    assert sheet.cell(row=2, column=1).value == "HYUNDAI/KIA/MOBIS|223112e100"  # SKU
                    assert sheet.cell(row=2, column=2).value == "HYUNDAI/KIA/MOBIS"  # Brand
                    assert sheet.cell(row=2, column=3).value == "223112e100"  # Article
                    assert sheet.cell(row=2, column=4).value == 100.50  # Price 1
                    assert sheet.cell(row=2, column=5).value == 5  # Quantity 1
                    assert sheet.cell(row=2, column=6).value == "Supplier A"  # Supplier 1

    @mock.patch('cross_dock.services.excel_service.query_supplier_data')
    def test_process_cross_dock_data_empty_results(self, mock_query_supplier_data):
        """Test handling of empty query results."""
        # Mock the query_supplier_data function to return empty results
        mock_query_supplier_data.return_value = pd.DataFrame(columns=["price", "quantity", "supplier_name"])

        # Test data
        test_data = [
            {"Бренд": "BRAND", "Артикул": "ARTICLE"}
        ]

        # Create a temporary directory for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock settings to use the temp directory
            with mock.patch('django.conf.settings.MEDIA_ROOT', temp_dir):
                with mock.patch('django.conf.settings.MEDIA_URL', '/media/'):
                    # Process the data
                    progress, file_url = process_cross_dock_data(test_data, "emex")

                    # Check the progress
                    assert progress == "100%"

                    # Check that the file exists
                    file_path = os.path.join(temp_dir, 'exports', os.path.basename(file_url))
                    assert os.path.exists(file_path)

                    # Load the workbook and check its contents
                    wb = load_workbook(file_path)
                    sheet = wb.active

                    # Check that empty cells are properly handled
                    assert sheet.cell(row=2, column=4).value is None  # Price 1
                    assert sheet.cell(row=2, column=5).value is None  # Quantity 1
                    assert sheet.cell(row=2, column=6).value is None  # Supplier 1

    @mock.patch('cross_dock.services.excel_service.query_supplier_data')
    def test_process_cross_dock_data_exception(self, mock_query_supplier_data):
        """Test error handling during data processing."""
        # Mock the query_supplier_data function to raise an exception
        mock_query_supplier_data.side_effect = Exception("Test exception")

        # Test data
        test_data = [
            {"Бренд": "BRAND", "Артикул": "ARTICLE"}
        ]

        # Create a temporary directory for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock settings to use the temp directory
            with mock.patch('django.conf.settings.MEDIA_ROOT', temp_dir):
                with mock.patch('django.conf.settings.MEDIA_URL', '/media/'):
                    # Process the data
                    progress, file_url = process_cross_dock_data(test_data, "emex")

                    # Check the progress
                    assert progress == "100%"

                    # Check that the file exists
                    file_path = os.path.join(temp_dir, 'exports', os.path.basename(file_url))
                    assert os.path.exists(file_path)

                    # Load the workbook and check its contents
                    wb = load_workbook(file_path)
                    sheet = wb.active

                    # Check that error cells are properly handled
                    assert sheet.cell(row=2, column=4).value is None  # Price 1
                    assert sheet.cell(row=2, column=5).value is None  # Quantity 1
                    assert sheet.cell(row=2, column=6).value is None  # Supplier 1
