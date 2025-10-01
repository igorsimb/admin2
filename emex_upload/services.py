import time
from pathlib import Path
from typing import Final

import pandas as pd
from loguru import logger

from common.utils.clickhouse import get_clickhouse_client

PROGRESS_SLEEP_SEC = 1
INSERT_CHUNK_SIZE = 500

# External-to-internal column mapping (Russian -> snake_case)
COLUMN_MAPPING: Final[dict[str, str]] = {
    "Дата": "date",
    "Арт": "article",
    "Бренд": "brand",
    "ЛогоПоставщика": "supplier_logo",
    "ИННПоставщика": "supplier_inn",
    "НаименованиПоставщика": "supplier_name",
    "Количество": "quantity",
    "ЦенаПокупки": "purchase_price",
    "СуммаПокупки": "purchase_total",
    "ЦенаПродажи": "sale_price",
    "СуммаПродажи": "sale_total",
    "Склад": "warehouse",
    "ЛогоКлиента": "client_logo",
    "ИННКлиента": "client_inn",
    "НазваниеКлиента": "client_name",
    "ЛогоПрайса": "price_logo",
}

# Final output order for ClickHouse insert
FINAL_COLUMNS_RU: Final[list[str]] = [
    "Дата",
    "Арт",
    "Бренд",
    "ЛогоПоставщика",
    "ИННПоставщика",
    "НаименованиПоставщика",
    "Количество",
    "ЦенаПокупки",
    "СуммаПокупки",
    "ЦенаПродажи",
    "СуммаПродажи",
    "Склад",
    "ЛогоКлиента",
    "ИННКлиента",
    "НазваниеКлиента",
    "ЛогоПрайса",
    "uploaded_at",
]

# ---------------------------------
# Helper: schema / header checking
# ---------------------------------


def validate_required_columns(df: pd.DataFrame) -> dict[str, list[str | int]]:
    """
    Ensure all expected Russian headers exist before any processing.
    """
    errors: dict[str, list[str | int]] = {"missing_columns": []}
    expected = set(COLUMN_MAPPING.keys())
    missing = sorted(list(expected - set(df.columns)))
    if missing:
        errors["missing_columns"] = missing
    return errors


# ---------------------------------------
# Helper: basic normalization & coercion
# ---------------------------------------


def rename_to_internal(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rename Russian headers to snake_case internal names for processing.
    """
    return df.rename(columns=COLUMN_MAPPING)


def coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cast columns to types compatible with ClickHouse DDL.
    """
    # Date -> Python date (ClickHouse: Date)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date

    # Quantity -> Int64 (invalid -> 0)
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0).astype(int)

    # Prices/totals -> Float64 (comma decimals supported; invalid -> 0.0)
    for col in ["purchase_price", "purchase_total", "sale_price", "sale_total"]:
        df[col] = (
            pd.to_numeric(df[col].astype(str).str.replace(",", ".", regex=False), errors="coerce")
            .fillna(0.0)
            .astype(float)
        )

    # String-like cols -> builtin str (avoid numpy scalars)
    string_cols = [
        "article",
        "brand",
        "supplier_logo",
        "supplier_inn",
        "supplier_name",
        "warehouse",
        "client_logo",
        "client_inn",
        "client_name",
        "price_logo",
    ]
    for col in string_cols:
        df[col] = df[col].astype("string").fillna("").astype(str)

    return df


# --------------------------------
# Helper: row-shape sanity check
# --------------------------------


class RowIntegrityValidator:
    """Categorizes and runs row-level integrity and type coercion checks."""

    def __init__(self, df: pd.DataFrame):
        self._df = df
        self._validations = {
            "Нечисловые значения в числовых колонках": self._validate_parse_loss,
            "Структурные ошибки (неверное количество колонок)": self._validate_column_count,
        }

    def _validate_column_count(self) -> set[int]:
        """
        Returns row indices where the number of columns is fewer than expected.
        This is detected by checking for null values in the last expected column
        before type coercion, as pandas fills missing cells with NaN.
        """
        last_col_internal = self._df.columns[-1]

        # Before coercion, missing values are NaN/None.
        # A null value in the last expected column strongly indicates a short row.
        bad_rows_mask = self._df[last_col_internal].isnull()

        if bad_rows_mask.any():
            offenders = set(self._df.index[bad_rows_mask])
            logger.warning(f"Found {len(offenders)} rows with suspected column count mismatch.")
            return offenders

        return set()

    def validate(self) -> dict[str, set[int]]:
        """Runs all integrity checks and returns a dictionary of results."""
        all_errors: dict[str, set[int]] = {}
        for name, validation_func in self._validations.items():
            bad_rows = validation_func()
            if bad_rows:
                all_errors[name] = bad_rows
        return all_errors

    @staticmethod
    def _is_coercible_float_str(s: str) -> bool:
        """
        Return True if string 's' can be parsed to a float after normalizing comma decimals; False otherwise.
        Empty strings return False.
        """
        s = s.strip().replace(",", ".")
        if s == "":
            return False
        try:
            float(s)
            return True
        except Exception:
            return False

    def _validate_parse_loss(self) -> set[int]:
        """
        Returns row indices where a numeric column contains a non-empty string
        that cannot be parsed into a number. This check should be run BEFORE type coercion.
        """
        logger.debug("--- Running _validate_parse_loss ---")
        numeric_cols = ["quantity", "purchase_price", "purchase_total", "sale_price", "sale_total"]
        offenders: set[int] = set()

        for c in numeric_cols:
            logger.debug(f"Checking column: '{c}'")
            try:
                # Find rows where the value is not an empty string but cannot be converted to a float.
                # The .astype(str) is important because a column might be all empty strings, which pandas can make dtype `float`
                values_as_str = self._df[c].astype(str)
                is_not_empty = values_as_str.str.strip().ne("")
                is_not_coercible = ~values_as_str.map(self._is_coercible_float_str)

                mask = is_not_empty & is_not_coercible

                if mask.any():
                    newly_found = self._df.index[mask]
                    logger.warning(
                        f"Found {len(newly_found)} parse-loss offenders in column '{c}' at indices: {list(newly_found)}"
                    )
                    offenders.update(newly_found)
                else:
                    logger.debug(f"No parse-loss offenders found in column '{c}'.")

            except Exception as e:
                logger.error(
                    f"An unexpected error occurred in _validate_parse_loss for column '{c}': {e}", exc_info=True
                )

        logger.debug(f"--- Finished _validate_parse_loss, total offenders: {len(offenders)} ---")
        return offenders


# --------------------------
# Helper: domain validation
# --------------------------


class BusinessLogicValidator:
    """
    Validates the business logic of the Emex sales data DataFrame.

    This class is designed to be easily extensible. To add a new validation rule:

    1.  **Create a new private method** within this class (e.g., `_validate_my_new_rule`).
        -   The method should accept `self` as its only argument. The DataFrame is
            accessible via `self._df`.
        -   It must return a `set` of row indices that fail the validation.

    2.  **Register the new method** by adding a descriptive key and a reference
       to it in the `self._validations` dictionary in the `__init__` method.

    The main `validate()` method will automatically execute it and aggregate the results.
    """

    def __init__(self, df: pd.DataFrame):
        self._df = df
        self._validations = {
            "Проверка формата колонки 'склад'": self._validate_warehouse_values,
            # "Проверка формата ИНН": self._validate_inn_format,
            "Проверка, что если кол-во > 0 и цена >0, то общая сумма > 0": self._validate_sales_data,
            "Проверка, что кол-во * цена = общая сумма": self._validate_totals,
        }

    def validate(self) -> dict[str, set[int]]:
        """
        Runs all registered checks and returns a de-duplicated dictionary mapping
        error types to sets of failed row indices. Once a row fails a check,
        it is not reported in subsequent checks.
        """
        all_errors: dict[str, set[int]] = {}
        for name, validation_func in self._validations.items():
            bad_rows = validation_func()
            if bad_rows:
                all_errors[name] = bad_rows

        # De-duplicate errors to ensure one row is only reported once
        clean_errors: dict[str, set[int]] = {}
        reported_indices: set[int] = set()

        for name, error_indices in all_errors.items():
            # Find indices that have not been reported yet
            new_failures = error_indices - reported_indices
            if new_failures:
                clean_errors[name] = new_failures
                # Add the newly reported indices to the set of all reported ones
                reported_indices.update(new_failures)

        return clean_errors

    def _validate_warehouse_values(self) -> set[int]:
        """Checks that 'warehouse' is either 'ДА' or 'НЕТ'."""
        bad_rows = ~self._df["warehouse"].isin(["ДА", "НЕТ"])
        return set(self._df.index[bad_rows])

    def _validate_sales_data(self) -> set[int]:
        """
        Checks for logical inconsistencies in totals:
        - If qty > 0 and purchase_price > 0, purchase_total must be > 0.
        - If qty > 0 and sale_price > 0, sale_total must be > 0.
        """
        qty_pos = self._df["quantity"] > 0

        # Check purchase totals
        purchase_price_pos = self._df["purchase_price"] > 0.0
        bad_purchase = qty_pos & purchase_price_pos & (self._df["purchase_total"] <= 0.0)

        # Check sale totals
        sale_price_pos = self._df["sale_price"] > 0.0
        bad_sale = qty_pos & sale_price_pos & (self._df["sale_total"] <= 0.0)

        return set(self._df.index[bad_purchase | bad_sale])

    def _validate_inn_format(self) -> set[int]:
        """
        CURRENTLY DISABLED UNTIL THE NEED ARISES!
        Checks that INN fields are 10 or 12 digits (if not empty)."""
        bad_rows: set[int] = set()
        for inn_col in ["supplier_inn", "client_inn"]:
            non_empty = self._df[inn_col].str.strip() != ""
            bad_inn = ~self._df[inn_col].astype(str).str.fullmatch(r"\d{10}|\d{12}") & non_empty
            if bad_inn.any():
                bad_rows.update(self._df.index[bad_inn])
        return bad_rows

    def _validate_totals(self) -> set[int]:
        """Validates that quantity * price = total."""
        purchase_bad = (self._df["quantity"] * self._df["purchase_price"]).round(2) != self._df["purchase_total"].round(
            2
        )
        sale_bad = (self._df["quantity"] * self._df["sale_price"]).round(2) != self._df["sale_total"].round(2)
        invalid_rows = self._df[purchase_bad | sale_bad]
        return set(invalid_rows.index)


# ------------------------------------------
# Helper: aggregate + drop invalid row idxs
# ------------------------------------------


def get_all_invalid_row_indices(errors: dict) -> set[int]:
    """
    Aggregate all row-level error indices across buckets.
    """
    bad_rows: set[int] = set()
    for key, value in errors.items():
        # Updated to handle nested dicts from validators
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                bad_rows.update(sub_value)
        elif isinstance(value, (list, set)):
            bad_rows.update(value)
    return bad_rows


# ------------------------------------------
# Helper: finalize for ClickHouse insertion
# ------------------------------------------


def rename_for_clickhouse(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rename internal names back to Russian headers and enforce final column order.
    """
    inverted = {v: k for k, v in COLUMN_MAPPING.items()}
    df = df.rename(columns=inverted)
    df = df[FINAL_COLUMNS_RU]
    return df


# -----------------
# Orchestrators
# -----------------


def validate_file_and_animate_progress(file_obj, task):
    """
    Performs a full, memory-safe validation and sends timed, sequential updates to the UI.
    """
    yields = lambda meta: task.update_state(state="PROGRESS", meta=meta)

    # --- DETECT ENCODING ---
    file_obj.seek(0)
    encoding = "utf-8"
    try:
        # Try to decode a small chunk to determine the encoding
        file_obj.read(1024).decode("utf-8")
    except UnicodeDecodeError:
        encoding = "windows-1251"
    finally:
        file_obj.seek(0)  # Always rewind after the check

    # --- COUNT TOTAL LINES ---
    # Quickly count total lines in the file to find structural errors later
    total_data_lines = sum(1 for _ in file_obj) - 1  # Subtract header
    file_obj.seek(0)

    # --- PHASE 1: SETUP AND PRE-CHECKS ---
    # 1. Reading File Step
    yields({"step": "Reading File", "status": "IN_PROGRESS"})
    time.sleep(PROGRESS_SLEEP_SEC)
    try:
        file_obj.seek(0)
        if not file_obj.read(1024).strip():
            yields({"step": "Reading File", "status": "FAILURE", "details": {"file_read_error": ["Файл пуст"]}})
            return {}, 0, 0
        file_obj.seek(0)
    except Exception as e:
        yields({"step": "Reading File", "status": "FAILURE", "details": {"file_read_error": [str(e)]}})
        yield {
            "status": "COMPLETE",
            "result": {
                "original_row_count": 0,
                "problematic_row_count": 0,
                "error_summary": {"file_read_error": [str(e)]},
            },
        }
        return
    yields({"step": "Reading File", "status": "SUCCESS"})
    time.sleep(PROGRESS_SLEEP_SEC)

    # 2. Header Validation
    yields({"step": "Header Validation", "status": "IN_PROGRESS"})
    time.sleep(PROGRESS_SLEEP_SEC)
    try:
        header_df = pd.read_csv(file_obj, sep="\t", engine="c", nrows=0, encoding=encoding)  # Reads only header
        header_errors = validate_required_columns(header_df)
        if header_errors.get("missing_columns"):
            yields({"step": "Header Validation", "status": "FAILURE", "details": header_errors})
            yield {
                "status": "COMPLETE",
                "result": {
                    "original_row_count": 0,
                    "problematic_row_count": 0,
                    "error_summary": header_errors,
                },
            }
            return
    except Exception as e:
        yields({"step": "Header Validation", "status": "FAILURE", "details": {"header_read_error": str(e)}})
        yield {
            "status": "COMPLETE",
            "result": {
                "original_row_count": 0,
                "problematic_row_count": 0,
                "error_summary": {"header_read_error": str(e)},
            },
        }
        return
    yields({"step": "Header Validation", "status": "SUCCESS"})
    time.sleep(PROGRESS_SLEEP_SEC)

    # --- PHASE 2: CHUNKED VALIDATION (COMPUTATION) ---
    yields({"step": "Row Integrity & Type Coercion", "status": "IN_PROGRESS"})
    # time.sleep(PROGRESS_SLEEP_SEC)
    yields(
        {
            "step": "Row Integrity & Type Coercion",
            "sub_step_name": "Проверка структуры файла",
            "sub_step_index": 0,
            "status": "IN_PROGRESS",
        }
    )
    time.sleep(PROGRESS_SLEEP_SEC)

    file_obj.seek(0)  # Rewind file before main chunked read
    CHUNKSIZE = 50000
    total_rows_processed = 0
    all_problematic_indices = set()
    final_errors = {"integrity_errors": {}, "business_errors": {}}
    clean_chunks = []

    dummy_df = pd.DataFrame(columns=COLUMN_MAPPING.values())
    integrity_validator_template = RowIntegrityValidator(dummy_df)
    business_validator_template = BusinessLogicValidator(dummy_df)
    integrity_checks = list(integrity_validator_template._validations.keys())
    business_checks = list(business_validator_template._validations.keys())
    aggregated_error_counts = dict.fromkeys(["structure_errors"] + integrity_checks + business_checks, 0)

    chunk_iterator = pd.read_csv(
        file_obj,
        sep="\t",
        on_bad_lines="warn",
        chunksize=CHUNKSIZE,
        engine="c",
        low_memory=False,
        header=0,
        encoding=encoding,
        dtype=str,
    )

    for df_chunk in chunk_iterator:
        chunk_starting_index = total_rows_processed
        df_chunk.index = range(chunk_starting_index + 1, chunk_starting_index + 1 + len(df_chunk))
        total_rows_processed += len(df_chunk)

        if df_chunk.empty:
            continue

        df_processed = rename_to_internal(df_chunk.copy())

        # Perform integrity validation BEFORE type coercion to catch parse-loss errors.
        integrity_validator = RowIntegrityValidator(df_processed)
        integrity_errors = integrity_validator.validate()
        for check_name, errors in integrity_errors.items():
            aggregated_error_counts[check_name] += len(errors)
            all_problematic_indices.update(errors)

        # Exclude rows with integrity errors before running business logic
        rows_with_integrity_errors = get_all_invalid_row_indices({"integrity": integrity_errors})
        df_clean_integrity = df_processed.drop(index=rows_with_integrity_errors, errors="ignore")

        # Now, coerce types for business logic checks and final insertion.
        df_coerced = coerce_types(df_clean_integrity)

        business_validator = BusinessLogicValidator(df_coerced)
        business_errors = business_validator.validate()
        for check_name, errors in business_errors.items():
            aggregated_error_counts[check_name] += len(errors)
            all_problematic_indices.update(errors)

        # Get the final clean chunk by dropping rows that failed business logic
        rows_with_business_errors = get_all_invalid_row_indices({"business": business_errors})
        df_clean_chunk = df_coerced.drop(index=rows_with_business_errors, errors="ignore")
        clean_chunks.append(df_clean_chunk)

    # --- FINALIZE AND SAVE CLEAN DATA ---
    if clean_chunks:
        final_clean_df = pd.concat(clean_chunks, ignore_index=True)
    else:
        final_clean_df = pd.DataFrame() # empty dataframe

    clean_file_path = None
    if not final_clean_df.empty:
        # Add uploaded_at column and rename for ClickHouse
        final_clean_df["uploaded_at"] = pd.to_datetime("now", utc=True).date()
        final_clean_df = rename_for_clickhouse(final_clean_df)

        # Save the clean DataFrame to a new temporary file
        original_path = Path(file_obj.name)
        clean_filename = f"{original_path.stem}.clean.pkl"
        temp_dir = original_path.parent
        clean_file_path = temp_dir / clean_filename
        final_clean_df.to_pickle(clean_file_path)

    # --- CALCULATE AND ANIMATE STRUCTURAL ERRORS ---
    # Combine the two types of structural errors (too many columns vs. too few) into a single count.
    num_bad_rows_too_few = aggregated_error_counts.get("Структурные ошибки (неверное количество колонок)", 0)
    total_structural_errors = (total_data_lines - total_rows_processed) + num_bad_rows_too_few
    aggregated_error_counts["structure_errors"] = total_structural_errors

    # Remove the specific "too few" check from the list to avoid reporting it separately.
    if "Структурные ошибки (неверное количество колонок)" in integrity_checks:
        integrity_checks.remove("Структурные ошибки (неверное количество колонок)")


    # --- PHASE 3: ANIMATE THE RESULTS ---
    status = "FAILURE" if total_structural_errors > 0 else "SUCCESS"
    yields(
        {
            "step": "Row Integrity & Type Coercion",
            "sub_step_name": "Проверка структуры файла",
            "sub_step_index": 0,
            "status": status,
            "details": {"message": f"Строк с ошибками: {total_structural_errors}" if status == "FAILURE" else "OK"},
        }
    )
    time.sleep(PROGRESS_SLEEP_SEC)

    has_integrity_errors = total_structural_errors > 0
    for index, check_name in enumerate(integrity_checks):
        yields(
            {
                "step": "Row Integrity & Type Coercion",
                "sub_step_index": index + 1,
                "sub_step_name": check_name,
                "status": "IN_PROGRESS",
            }
        )
        time.sleep(PROGRESS_SLEEP_SEC)
        final_count = aggregated_error_counts[check_name]
        status = "FAILURE" if final_count > 0 else "SUCCESS"
        if status == "FAILURE":
            has_integrity_errors = True
        yields(
            {
                "step": "Row Integrity & Type Coercion",
                "sub_step_index": index + 1,
                "sub_step_name": check_name,
                "status": status,
                "details": {"message": f"Строк с ошибками: {final_count}" if status == "FAILURE" else "OK"},
            }
        )
        time.sleep(PROGRESS_SLEEP_SEC)

    yields({"step": "Row Integrity & Type Coercion", "status": "FAILURE" if has_integrity_errors else "SUCCESS"})
    time.sleep(PROGRESS_SLEEP_SEC)

    # 4. Business Rule Validation
    yields({"step": "Business Rule Validation", "status": "IN_PROGRESS"})
    time.sleep(PROGRESS_SLEEP_SEC)
    has_business_errors = False
    for index, check_name in enumerate(business_checks):
        yields(
            {
                "step": "Business Rule Validation",
                "sub_step_index": index,
                "sub_step_name": check_name,
                "status": "IN_PROGRESS",
            }
        )
        time.sleep(PROGRESS_SLEEP_SEC)
        final_count = aggregated_error_counts.get(check_name, 0)
        status = "FAILURE" if final_count > 0 else "SUCCESS"
        if status == "FAILURE":
            has_business_errors = True
        yields(
            {
                "step": "Business Rule Validation",
                "sub_step_index": index,
                "sub_step_name": check_name,
                "status": status,
                "details": {"message": f"Строк с ошибками: {final_count}" if status == "FAILURE" else "OK"},
            }
        )
        time.sleep(PROGRESS_SLEEP_SEC)

    yields({"step": "Business Rule Validation", "status": "FAILURE" if has_business_errors else "SUCCESS"})
    time.sleep(PROGRESS_SLEEP_SEC)

    # 5. Final Result
    for name in integrity_checks:
        final_errors["integrity_errors"][name] = aggregated_error_counts[name]
    for name in business_checks:
        final_errors["business_errors"][name] = aggregated_error_counts[name]

    yield {
        "status": "COMPLETE",
        "result": {
            "original_row_count": total_rows_processed + 1,  # Add 1 for header
            "problematic_row_count": (total_data_lines - total_rows_processed) + len(all_problematic_indices),
            "error_summary": final_errors,
            "clean_file_path": str(clean_file_path) if clean_file_path else None,
        },
    }


def insert_data_to_clickhouse(df: pd.DataFrame, task=None) -> tuple[bool, str]:
    """
    Inserts a DataFrame into the `sup_stat.emex_dif` table in ClickHouse,
    optionally reporting progress back to a Celery task.
    """
    total_rows = len(df)
    if total_rows == 0:
        return True, "Нет данных для загрузки."

    try:
        with get_clickhouse_client(readonly=0) as client:
            # Insert in chunks to allow for progress reporting
            for i in range(0, total_rows, INSERT_CHUNK_SIZE):
                chunk = df.iloc[i:i + INSERT_CHUNK_SIZE]
                client.insert_df("sup_stat.emex_dif", chunk)

                if task:
                    processed_rows = i + len(chunk)
                    progress = int((processed_rows / total_rows) * 100)
                    task.update_state(
                        state='PROGRESS',
                        meta={'step': 'INSERTING', 'status': 'IN_PROGRESS', 'progress': progress}
                    )
            
            return True, f"Успешно загружено {total_rows} строк."

    except Exception as e:
        logger.error("An error occurred with ClickHouse operation: {}\n", e)
        return False, f"Failed to insert data: {e}"
