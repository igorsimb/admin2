from unittest.mock import MagicMock, patch

import pandas as pd

from emex_upload.services import process_emex_file


class TestProcessEmexFile:
    def test_process_valid_file(self):
        """Test processing a perfectly valid TSV file."""
        valid_data = (
            "Дата\tАрт\tБренд\tЛогоПоставщика\tЛогоПрайса\tИННПоставщика\tНаименованиПоставщика\tКоличество\tЦенаПокупки\tСуммаПокупки\tЦенаПродажи\tСуммаПродажи\tСклад\tЛогоКлиента\tИННКлиента\tНазваниеКлиента\n"
            "2025-05-01 00:04:39.580\t1751210000\tHyundai / KIA\tOJVU\tOJVA\t9723029696\tООО НеликвидаНет\t2\t17\t34\t38,4\t76,8\tДА\tSVER\t6432019850\tООО \"ЕМЕХ-ПОВОЛЖЬЕ\"\n"
            "2025-05-01 00:03:07.600\t31106893549\tBMW\tSAPV\tSAPV\t5032360171\tООО КАРПАРТС\t1\t12000\t12000\t13386\t13386\tДА\tSXIX\t614107900565\tИП Малахов Андрей Дмитриевич\n"
        )

        file_obj = MagicMock()
        file_obj.read.return_value = valid_data.encode("utf-8")

        df, errors, original_count, dropped_count = process_emex_file(file_obj)

        assert df is not None
        assert original_count == 2
        assert dropped_count == 0
        assert len(df) == 2
        assert all(e == [] for e in errors.values())
        assert "uploaded_at" in df.columns
        assert df["Количество"].iloc[0] == 2

    def test_file_with_missing_columns(self):
        """Test a file that is missing some columns."""
        invalid_data = (
            "Дата\tАрт\tБренд\tКоличество\tЦенаПокупки\n"
            "2025-05-01 00:04:39.580\t1751210000\tHyundai / KIA\t2\t17\n"
        )

        file_obj = MagicMock()
        file_obj.read.return_value = invalid_data.encode("utf-8")

        df, errors, original_count, dropped_count = process_emex_file(file_obj)

        assert df is None
        assert original_count == 1
        assert dropped_count == 1
        assert "missing_columns" in errors
        assert len(errors["missing_columns"]) > 0
        assert "ИННКлиента" in errors["missing_columns"]

    def test_file_with_calculation_errors(self):
        """Test a file where totals do not match quantity * price."""
        invalid_data = (
            "Дата\tАрт\tБренд\tЛогоПоставщика\tЛогоПрайса\tИННПоставщика\tНаименованиПоставщика\tКоличество\tЦенаПокупки\tСуммаПокупки\tЦенаПродажи\tСуммаПродажи\tСклад\tЛогоКлиента\tИННКлиента\tНазваниеКлиента\n"
            "2025-05-01 00:04:39.580\t1751210000\tHyundai / KIA\tOJVU\tOJVA\t9723029696\tООО НеликвидаНет\t2\t17\t35\t38,4\t76,8\tДА\tSVER\t6432019850\tООО \"ЕМЕХ-ПОВОЛЖЬЕ\"\n"
            "2025-05-01 00:03:07.600\t31106893549\tBMW\tSAPV\tSAPV\t5032360171\tООО КАРПАРТС\t1\t12000\t12000\t13386\t13386\tДА\tSXIX\t614107900565\tИП Малахов Андрей Дмитриевич\n"
        )

        file_obj = MagicMock()
        file_obj.read.return_value = invalid_data.encode("utf-8")

        df, errors, original_count, dropped_count = process_emex_file(file_obj)

        assert df is not None
        assert original_count == 2
        assert dropped_count == 1
        assert len(df) == 1
        assert "calculation_errors" in errors
        assert errors["calculation_errors"] == [0]  # First row (index 0) is invalid

    def test_safety_net_with_mixed_validity_data(self):
        """
        Tests the file processing with a mix of valid and invalid rows, serving as a safety-net.
        """
        file_content = (
            "Дата\tАрт\tБренд\tЛогоПоставщика\tЛогоПрайса\tИННПоставщика\tНаименованиПоставщика\tКоличество\tЦенаПокупки\tСуммаПокупки\tЦенаПродажи\tСуммаПродажи\tСклад\tЛогоКлиента\tИННКлиента\tНазваниеКлиента\n"
            "2025-10-02 08:58:52.457\tOK001\tGoodBrand\tRKOO\tRKOO\t132770491674\tООО Валид\t2\t100\t200\t150\t300\tДА\tOPAL\t352502398269\tИП Клиент Валидный\n"
            "2025-10-02 09:00:00.000\tBAD001\tBad1\tRKOO\tRKOO\t132770491674\tООО Ошибка1\t2\t50\t101\t120\t240\tДА\tOPAL\t352502398269\tИП Клиент Валидный\n"
            "2025-10-02 09:01:00.000\tBAD002\tBad2\tRKOO\tRKOO\t132770491674\tООО Ошибка2\t1\t300\t301\t400\t399\tДА\tOPAL\t352502398269\tИП Клиент Валидный\n"
            "2025-10-02 09:02:00.000\tBAD003\tBad3\tRKOO\tRKOO\t132770491674\tООО Ошибка3\t3\t200\t599\t250\t750\tДА\tOPAL\t352502398269\tИП Клиент Валидный\n"
            "2025-10-02 09:03:00.000\tBAD004\tBad4\tRKOO\tRKOO\t132770491674\tООО Ошибка4\t5\t10\t49\t20\t101\tДА\tOPAL\t352502398269\tИП Клиент Валидный\n"
            "2025-10-02 09:04:00.000\tBAD005\tBad5\tRKOO\tRKOO\t132770491674\tООО Ошибка5\t1\t77\t70\t88\t87\tДА\tOPAL\t352502398269\tИП Клиент Валидный\n"
            "2025-10-02 09:05:00.000\tBAD006\tBad6\tRKOO\tRKOO\t132770491674\tООО Ошибка6\t4\t25\t101\t30\t119\tДА\tOPAL\t352502398269\tИП Клиент Валидный\n"
            "2025-10-02 09:06:00.000\tBAD007\tBad7\tRKOO\tRKOO\t132770491674\tООО Ошибка7\t1\t200\t199\t300\t299\tДА\tOPAL\t352502398269\tИП Клиент Валидный\n"
            "2025-10-02 09:07:00.000\tBAD008\tBad8\tRKOO\tRKOO\t132770491674\tООО Ошибка8\t6\t15\t91\t20\t119\tДА\tOPAL\t352502398269\tИП Клиент Валидный\n"
        ).encode("utf-8")

        file_obj = MagicMock()
        file_obj.read.return_value = file_content

        df, errors, original_count, dropped_count = process_emex_file(file_obj)

        assert df is not None
        assert original_count == 9
        assert dropped_count == 8
        assert len(df) == 1
        assert df.iloc[0]["Арт"] == "OK001"
        assert len(errors.get("calculation_errors", [])) == 8
        assert set(errors.get("calculation_errors", [])) == {1, 2, 3, 4, 5, 6, 7, 8}


class TestInsertEmexData:
    @patch("emex_upload.services.get_clickhouse_client")
    def test_insert_success(self, mock_get_client):
        """Test successful data insertion."""
        mock_client = MagicMock()
        mock_context_manager = MagicMock()
        mock_context_manager.__enter__.return_value = mock_client
        mock_get_client.return_value = mock_context_manager

        data = {
            "Дата": ["2025-05-01"],
            "Арт": ["TESTART"],
            "Бренд": ["TESTBRAND"],
            "ЛогоПоставщика": ["LOGO"],
            "ИННПоставщика": ["123"],
            "НаименованиПоставщика": ["SUPPLIER"],
            "Количество": [1],
            "ЦенаПокупки": [100.0],
            "СуммаПокупки": [100.0],
            "ЦенаПродажи": [120.0],
            "СуммаПродажи": [120.0],
            "Склад": ["WH"],
            "ЛогоКлиента": ["CLOGO"],
            "ИННКлиента": ["456"],
            "НазваниеКлиента": ["CLIENT"],
            "ЛогоПрайса": ["PLOGO"],
            "uploaded_at": ["2025-10-03"],
        }
        df = pd.DataFrame(data)

        from emex_upload.services import insert_data_to_clickhouse

        success, message = insert_data_to_clickhouse(df)

        assert success is True
        assert message == f"Successfully inserted {len(df)} rows."
        mock_get_client.assert_called_once_with(readonly=0)
        mock_client.insert_df.assert_called_once_with("sup_stat.emex_dif", df)

    @patch("emex_upload.services.get_clickhouse_client")
    def test_insert_failure(self, mock_get_client):
        """Test insertion failure when the client raises an exception."""
        mock_client = MagicMock()
        mock_client.insert_df.side_effect = Exception("DB error")
        mock_context_manager = MagicMock()
        mock_context_manager.__enter__.return_value = mock_client
        mock_get_client.return_value = mock_context_manager

        df = pd.DataFrame({"Дата": ["2025-05-01"]})

        from emex_upload.services import insert_data_to_clickhouse

        success, message = insert_data_to_clickhouse(df)

        assert success is False
        assert "Failed to insert data: DB error" in message
        mock_get_client.assert_called_once_with(readonly=0)