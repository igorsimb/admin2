"""
Integration tests for cross-dock functionality.

This module contains integration tests for the cross-dock functionality,
testing the full workflow from file input to Excel output.
"""

import os
import tempfile
from unittest import mock

import pandas as pd
import pytest
from openpyxl import Workbook, load_workbook

from cross_dock.services.excel_service import process_cross_dock_data_from_file


class TestIntegration:
    """Integration test suite for cross-dock functionality."""

    @mock.patch('cross_dock.services.excel_service.query_supplier_data')
    def test_process_cross_dock_data_from_file(self, mock_query_supplier_data):
        """Test processing cross-dock data from a file."""
        mock_query_supplier_data.return_value = pd.DataFrame({
            "price": [100.50, 120.75, 90.25],
            "quantity": [5, 10, 3],
            "supplier_name": ["Supplier A", "Supplier B", "Supplier C"]
        })

        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as temp_file:
            temp_file_path = temp_file.name

        wb = Workbook()
        sheet = wb.active

        sheet.cell(row=1, column=1, value="Бренд")
        sheet.cell(row=1, column=2, value="Артикул")

        sheet.cell(row=2, column=1, value="HYUNDAI/KIA/MOBIS")
        sheet.cell(row=2, column=2, value="223112e100")
        sheet.cell(row=3, column=1, value="VAG")
        sheet.cell(row=3, column=2, value="000915105cd")

        wb.save(temp_file_path)

        try:
            output_file_path = process_cross_dock_data_from_file(temp_file_path, "emex")
            assert os.path.exists(output_file_path)

            wb = load_workbook(output_file_path)
            sheet = wb.active

            headers = ["SKU", "Бренд", "Артикул", "Лучшая цена 1", "Количество 1", "Название поставщика 1",
                    "Лучшая цена 2", "Количество 2", "Название поставщика 2",
                    "Лучшая цена 3", "Количество 3", "Название поставщика 3"]
            for col_num, header in enumerate(headers, start=1):
                assert sheet.cell(row=1, column=col_num).value == header

            assert sheet.cell(row=2, column=1).value == "HYUNDAI/KIA/MOBIS|223112e100"
            assert sheet.cell(row=2, column=2).value == "HYUNDAI/KIA/MOBIS"
            assert sheet.cell(row=2, column=3).value == "223112e100"
            assert sheet.cell(row=2, column=4).value == 100.50
            assert sheet.cell(row=2, column=5).value == 5
            assert sheet.cell(row=2, column=6).value == "Supplier A"

            os.unlink(output_file_path)
        finally:
            # Always clean up the input file
            os.unlink(temp_file_path)
