"""
Tests for Excel service.

This module contains tests for the Excel service functions that are used
for processing cross-dock data and generating Excel files.
"""

import json
import os
import tempfile
from unittest import mock

import pandas as pd
import pytest
from openpyxl import load_workbook

from cross_dock.services.excel_service import process_cross_dock_data


@pytest.fixture(autouse=True)
def mock_normalization():
    with mock.patch("cross_dock.services.excel_service.normalize_brand_sku_pairs") as normalize:
        normalize.side_effect = lambda pairs: [(b.strip().upper(), a.strip().upper()) for b, a in pairs]
        yield normalize


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
        mock.patch("cross_dock.services.excel_service.query_supplier_data_mv") as mock_query,
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
                [("invalid price", 5, "Supplier A", "BOSCH", "123")],
                columns=["price", "quantity", "supplier_name", "brand", "sku"],
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
        SimpleNamespace(result_rows=[(100.0, 5, "Supplier A", "BOSCH", "AB123")]),
        SimpleNamespace(result_rows=[]),
    ]
    with mock.patch("cross_dock.services.clickhouse_service.get_clickhouse_client") as mock_get:
        mock_get.return_value.__enter__.return_value = mock_http
        output = process_cross_dock_data_from_file(str(input_path), "ОПТ-2", use_mv=False)

    assert mock_get.call_count == 1
    assert mock_http.query.call_count == 3
    for call in mock_http.query.call_args_list[1:]:
        assert json.loads(call.kwargs["external_data"].files[0].data) == ["BOSCH", "AB123"]
    workbook = load_workbook(output)
    rows = list(workbook.active.values)
    assert len(rows) == 3
    assert rows[1][:3] == rows[2][:3] == (" BOSCH | AB123 ", " BOSCH ", " AB123 ")
    assert rows[1][3:6] == (100, 5, "Supplier A")
    assert rows[2][3:] == (None,) * 9


@pytest.mark.parametrize("use_mv", [False, True])
def test_aliases_and_duplicate_input_rows_use_canonical_pairs_without_changing_export(
    settings, tmp_path, mock_normalization, use_mv
):
    settings.MEDIA_ROOT = tmp_path
    mock_normalization.side_effect = None
    mock_normalization.return_value = [("HYUNDAI/KIA/MOBIS", "001A")] * 3
    data = [
        {"Бренд": " hyundai/kia ", "Артикул": "001a"},
        {"Бренд": "Hyundai/Kia/Mobis", "Артикул": "001A"},
        {"Бренд": " hyundai/kia ", "Артикул": "001a"},
    ]
    offers = pd.DataFrame([(100, 5, "Supplier A")], columns=["price", "quantity", "supplier_name"])
    with (
        mock.patch("cross_dock.services.excel_service.query_supplier_data_mv") as fast,
        mock.patch("cross_dock.services.excel_service.supplier_query_session") as session,
    ):
        fast.return_value = offers.assign(brand="HYUNDAI/KIA/MOBIS", sku="001A")
        slow = session.return_value.__enter__.return_value
        slow.return_value = offers
        _, url = process_cross_dock_data(data, "ОПТ-2", use_mv=use_mv)

    mock_normalization.assert_called_once_with([(item["Бренд"], item["Артикул"]) for item in data])
    if use_mv:
        fast.assert_called_once_with([("HYUNDAI/KIA/MOBIS", "001A")], "ОПТ-2")
        session.assert_not_called()
    else:
        assert slow.call_args_list == [mock.call("HYUNDAI/KIA/MOBIS", "001A")] * 3
        fast.assert_not_called()
    rows = list(load_workbook(tmp_path / "exports" / os.path.basename(url)).active.values)
    assert len(rows) == 4
    for row, original in zip(rows[1:], data, strict=True):
        assert row[1:3] == (original["Бренд"], original["Артикул"])
        assert row[3:6] == (100, 5, "Supplier A")


def test_normalization_failure_does_not_save_an_empty_report(mock_normalization):
    mock_normalization.side_effect = RuntimeError("Dictionary unavailable")
    with mock.patch("cross_dock.services.excel_service.save_workbook") as save:
        with pytest.raises(RuntimeError, match="Dictionary unavailable"):
            process_cross_dock_data([{"Бренд": "BOSCH", "Артикул": "123"}], "ОПТ-2", use_mv=True)
    save.assert_not_called()


@pytest.mark.parametrize("use_mv", [False, True])
def test_file_input_preserves_leading_zeros_and_literal_na(tmp_path, use_mv):
    from cross_dock.services.excel_service import process_cross_dock_data_from_file

    path = tmp_path / "input.xlsx"
    pd.DataFrame({"Бренд": ["NA", "BOSCH"], "Артикул": ["00123", "1E3354697011"]}).to_excel(path, index=False)
    with mock.patch("cross_dock.services.excel_service.process_cross_dock_data") as process:
        process.return_value = ("100%", "/media/exports/result.xlsx")
        process_cross_dock_data_from_file(str(path), "ОПТ-2", use_mv=use_mv)
    assert process.call_args.args[0] == [
        {"Бренд": "NA", "Артикул": "00123"},
        {"Бренд": "BOSCH", "Артикул": "1E3354697011"},
    ]
