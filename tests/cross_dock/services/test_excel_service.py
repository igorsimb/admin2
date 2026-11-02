"""
Tests for Excel service.

This module contains tests for the Excel service functions that are used
for processing cross-dock data and generating Excel files.
"""

import os
import tempfile
from unittest import mock

import pandas as pd
import pytest
from openpyxl import load_workbook

from cross_dock.services.excel_service import process_cross_dock_data


class TestExcelService:
    """Test suite for Excel service functions."""

    @mock.patch("cross_dock.services.excel_service.supplier_query_session")
    def test_process_cross_dock_data(self, mock_session):
        """Test processing cross-dock data and generating an Excel file."""
        mock_query_supplier_data = mock_session.return_value.__enter__.return_value
        mock_query_supplier_data.return_value = pd.DataFrame(
            {
                "price": [100.50, 120.75, 90.25],
                "quantity": [5, 10, 3],
                "supplier_name": ["Supplier A", "Supplier B", "Supplier C"],
            }
        )

        test_data = [
            {"Бренд": "HYUNDAI/KIA/MOBIS", "Артикул": "223112e100"},
            {"Бренд": "VAG", "Артикул": "000915105cd"},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch("django.conf.settings.MEDIA_ROOT", temp_dir):
                with mock.patch("django.conf.settings.MEDIA_URL", "/media/"):
                    progress, file_url = process_cross_dock_data(test_data, "Группа для проценки ТРЕШКА")
                    assert progress == "100%"

                    file_path = os.path.join(temp_dir, "exports", os.path.basename(file_url))
                    assert os.path.exists(file_path)

                    wb = load_workbook(file_path)
                    sheet = wb.active

                    headers = [
                        "SKU",
                        "Бренд",
                        "Артикул",
                        "Лучшая цена 1",
                        "Количество 1",
                        "Название поставщика 1",
                        "Лучшая цена 2",
                        "Количество 2",
                        "Название поставщика 2",
                        "Лучшая цена 3",
                        "Количество 3",
                        "Название поставщика 3",
                    ]
                    for col_num, header in enumerate(headers, start=1):
                        assert sheet.cell(row=1, column=col_num).value == header

                    assert sheet.cell(row=2, column=1).value == "HYUNDAI/KIA/MOBIS|223112e100"
                    assert sheet.cell(row=2, column=2).value == "HYUNDAI/KIA/MOBIS"
                    assert sheet.cell(row=2, column=3).value == "223112e100"
                    assert sheet.cell(row=2, column=4).value == 100.50
                    assert sheet.cell(row=2, column=5).value == 5
                    assert sheet.cell(row=2, column=6).value == "Supplier A"

    @mock.patch("cross_dock.services.excel_service.supplier_query_session")
    def test_process_cross_dock_data_empty_results(self, mock_session):
        """Test handling of empty query results."""
        mock_query_supplier_data = mock_session.return_value.__enter__.return_value
        mock_query_supplier_data.return_value = pd.DataFrame(columns=["price", "quantity", "supplier_name"])

        test_data = [{"Бренд": "BRAND", "Артикул": "ARTICLE"}]

        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch("django.conf.settings.MEDIA_ROOT", temp_dir):
                with mock.patch("django.conf.settings.MEDIA_URL", "/media/"):
                    progress, file_url = process_cross_dock_data(test_data, "Группа для проценки ТРЕШКА")
                    assert progress == "100%"

                    file_path = os.path.join(temp_dir, "exports", os.path.basename(file_url))
                    assert os.path.exists(file_path)

                    wb = load_workbook(file_path)
                    sheet = wb.active

                    # Verify empty cells are handled properly
                    assert sheet.cell(row=2, column=4).value is None
                    assert sheet.cell(row=2, column=5).value is None
                    assert sheet.cell(row=2, column=6).value is None

    @mock.patch("cross_dock.services.excel_service.supplier_query_session")
    def test_process_cross_dock_data_exception(self, mock_session):
        """Test error handling during data processing."""
        mock_query_supplier_data = mock_session.return_value.__enter__.return_value
        mock_query_supplier_data.side_effect = Exception("Test exception")

        test_data = [{"Бренд": "BRAND", "Артикул": "ARTICLE"}]

        with mock.patch("cross_dock.services.excel_service.save_workbook") as mock_save:
            with pytest.raises(Exception, match="Test exception"):
                process_cross_dock_data(test_data, "Группа для проценки ТРЕШКА")
        mock_save.assert_not_called()


@pytest.mark.parametrize("failure", ["query", "input", "export"])
def test_fast_report_does_not_save_incomplete_workbook(failure):
    data = [{"Бренд": "BOSCH", "Артикул": "123"}]
    with (
        mock.patch("cross_dock.services.clickhouse_service.query_supplier_data_mv") as mock_query,
        mock.patch("cross_dock.services.excel_service.save_workbook") as mock_save,
    ):
        if failure == "query":
            mock_query.side_effect = RuntimeError("Query failed")
            expected_error = RuntimeError
        elif failure == "input":
            data = [{"Бренд": "BOSCH"}]
            expected_error = KeyError
        else:
            mock_query.return_value = pd.DataFrame(
                [("invalid price", 5, "Supplier A", "bosch", "123")],
                columns=["price", "quantity", "supplier_name", "brand_lower", "sku_lower"],
            )
            expected_error = ValueError

        with pytest.raises(expected_error):
            process_cross_dock_data(data, "ОПТ-2", use_mv=True)

    mock_save.assert_not_called()


def test_slow_report_preserves_duplicate_rows_and_input_whitespace(settings, tmp_path):
    from types import SimpleNamespace

    from clickhouse_connect.driver.httpclient import HttpClient

    from cross_dock.services.excel_service import process_cross_dock_data_from_file

    settings.MEDIA_ROOT = tmp_path
    input_path = tmp_path / "input.xlsx"
    pd.DataFrame({"Бренд": [" BOSCH ", " BOSCH "], "Артикул": [" AB123 ", " AB123 "]}).to_excel(input_path, index=False)
    mock_http = mock.create_autospec(HttpClient, instance=True, spec_set=True)
    mock_http.query.side_effect = [
        SimpleNamespace(result_rows=[(1,)]),
        SimpleNamespace(result_rows=[(100.0, 5, "Supplier A")]),
        SimpleNamespace(result_rows=[]),
    ]
    with mock.patch("cross_dock.services.clickhouse_service.get_clickhouse_client") as mock_get:
        mock_get.return_value.__enter__.return_value = mock_http
        output = process_cross_dock_data_from_file(str(input_path), "ОПТ-2", use_mv=False)

    assert mock_get.call_count == 1
    assert mock_http.query.call_count == 3
    for call in mock_http.query.call_args_list[1:]:
        assert call.kwargs["parameters"]["brand_values"] == (" bosch ",)
        assert call.kwargs["parameters"]["sku_lower"] == " ab123 "
    workbook = load_workbook(output)
    rows = list(workbook.active.values)
    assert len(rows) == 3
    assert rows[1][:3] == rows[2][:3] == (" BOSCH | AB123 ", " BOSCH ", " AB123 ")
    assert rows[1][3:6] == (100, 5, "Supplier A")
    assert rows[2][3:] == (None,) * 9
