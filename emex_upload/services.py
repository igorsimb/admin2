import datetime
import io
from typing import Final

import time

import pandas as pd
from django.core.files.uploadedfile import UploadedFile
from loguru import logger

from common.utils.clickhouse import get_clickhouse_client

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


# -----------------------
# Helper: low-level I/O
# -----------------------

def get_dataframe_from_file(file_obj: UploadedFile) -> tuple[pd.DataFrame | None, bytes, dict[str, list[str | int]]]:
    """
    Read the uploaded file as TSV trying UTF-8 then Windows-1251.
    Returns (df_or_none, raw_bytes, errors).
    """
    file_bytes = file_obj.read()
    read_kwargs = {"sep": "\t", "low_memory": False}

    try:
        df = pd.read_csv(io.BytesIO(file_bytes), encoding="utf-8", **read_kwargs)
    except UnicodeDecodeError:
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), encoding="windows-1251", **read_kwargs)
        except Exception as e:
            return None, file_bytes, {"file_read_error": [f"Не удалось прочитать файл в кодировках UTF-8 и windows-1251. Ошибка: {e}"]}
    except Exception as e:
        return None, file_bytes, {"file_read_error": [str(e)]}

    df.dropna(how="all", inplace=True)
    return df, file_bytes, {}


# ---------------------------------
# Helper: schema / header checking
# ---------------------------------

def validate_required_columns(df: pd.DataFrame) -> dict[str, list[str | int]]:
    """
    Ensure all expected Russian headers exist before any processing.
    """
    errors: dict[str, list[str | int]] = {"missing_columns": [], "calculation_errors": []}
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

def detect_row_length_mismatch(file_bytes: bytes) -> list[int]:
    """
    Count tabs per line vs header to detect misaligned rows.
    Uses raw bytes to avoid pandas masking issues.
    """
    expected_tabs = len(COLUMN_MAPPING) - 1

    # Try UTF-8 then cp1251; ignore undecodable bytes to keep counting.
    raw_text = file_bytes.decode("utf-8", errors="ignore")
    if "\t" not in raw_text:
        raw_text = file_bytes.decode("windows-1251", errors="ignore")

    lines = [ln for ln in raw_text.splitlines() if ln.strip()]
    if not lines:
        return []

    body = lines[1:]  # skip header
    bad_rows = [i for i, ln in enumerate(body) if ln.count("\t") != expected_tabs]
    return bad_rows


# --------------------------------
# Helper: parse-loss detection
# --------------------------------

def is_coercible_float_str(s: str) -> bool:
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


def find_numeric_parse_loss_rows(df: pd.DataFrame) -> list[int]:
    """
    Return row indices where a non-empty, non-numeric string in a numeric column
    was coerced to 0.0 during parsing (i.e., parse-loss occurred).
    Columns checked: purchase_price, purchase_total, sale_price, sale_total.
    """
    numeric_cols = ["purchase_price", "purchase_total", "sale_price", "sale_total"]
    raw_numeric = {c: df[c].astype(str) for c in numeric_cols}

    offenders: set[int] = set()
    for c in numeric_cols:
        mask = (df[c] == 0.0) & raw_numeric[c].str.strip().ne("") & (~raw_numeric[c].map(is_coercible_float_str))
        if mask.any():
            offenders.update(df.index[mask].tolist())
    return sorted(offenders)


# --------------------------
# Helper: domain validation
# --------------------------

def validate_business_rules(df: pd.DataFrame) -> list[int]:
    """
    Return a flat list of row indices that violate business/value-domain rules:
      - warehouse ∈ {"ДА","НЕТ"}
      - if quantity > 0 then sale_price > 0 and sale_total > 0
      - INN fields are either 10 or 12 digits (when non-empty)
    """
    bad_rows: set[int] = set()

    bad_warehouse = ~df["warehouse"].isin(["ДА", "НЕТ"])
    if bad_warehouse.any():
        bad_rows.update(df.index[bad_warehouse].tolist())

    qty_pos = df["quantity"] > 0
    missing_sale = qty_pos & ((df["sale_price"] <= 0.0) | (df["sale_total"] <= 0.0))
    if missing_sale.any():
        bad_rows.update(df.index[missing_sale].tolist())

    for inn_col in ["supplier_inn", "client_inn"]:
        non_empty = df[inn_col].str.strip() != ""
        bad_inn = ~df[inn_col].astype(str).str.fullmatch(r"\d{10}|\d{12}") & non_empty
        if bad_inn.any():
            bad_rows.update(df.index[bad_inn].tolist())

    return sorted(bad_rows)


# -----------------------------
# Helper: calculation checks
# -----------------------------

def run_calculation_checks(df: pd.DataFrame) -> list[int]:
    """
    Validate purchase/sale totals vs quantity * unit price (rounded to 2 decimals).
    """
    purchase_bad = (df["quantity"] * df["purchase_price"]).round(2) != df["purchase_total"].round(2)
    sale_bad = (df["quantity"] * df["sale_price"]).round(2) != df["sale_total"].round(2)
    invalid = df[purchase_bad | sale_bad]
    return invalid.index.tolist()


# ------------------------------------------
# Helper: aggregate + drop invalid row idxs
# ------------------------------------------

def get_all_invalid_row_indices(errors: dict) -> set[int]:
    """
    Aggregate all row-level error indices across buckets.
    """
    bad_rows: set[int] = set(errors.get("calculation_errors", []))
    bad_rows.update(errors.get("row_length_mismatch", []))
    bad_rows.update(errors.get("parse_errors", []))
    bad_rows.update(errors.get("domain_errors", []))
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

def get_validation_summary(
    file_obj: UploadedFile, task=None
) -> tuple[dict[str, list[str | int]], int, int, pd.DataFrame | None]:
    """
    Orchestrates all validation checks and returns a summary of errors
    without modifying the DataFrame.

    Args:
        file_obj: The uploaded file object.
        task: An optional Celery task instance for progress reporting.

    Returns:
        - errors: Dictionary of validation errors.
        - original_row_count: Total rows in the original file.
        - problematic_row_count: Count of unique rows with errors.
        - df: The processed DataFrame (with types coerced) but before dropping rows.
    """
    if task:
        task.update_state(state="PROGRESS", meta={"step": "Reading File", "status": "IN_PROGRESS"})
    df_read, file_bytes, errors = get_dataframe_from_file(file_obj)
    if df_read is None:
        if task:
            task.update_state(state="FAILURE", meta={"step": "Reading File", "status": "FAILURE", "details": errors})
        return errors, 0, 0, None
    if task:
        task.update_state(state="PROGRESS", meta={"step": "Reading File", "status": "SUCCESS"})
        time.sleep(2)

    original_row_count = len(df_read)

    # Header Validation
    if task:
        task.update_state(state="PROGRESS", meta={"step": "Header Validation", "status": "IN_PROGRESS"})
    header_errors = validate_required_columns(df_read)
    if header_errors.get("missing_columns"):
        errors.update(header_errors)
        if task:
            task.update_state(state="FAILURE", meta={"step": "Header Validation", "status": "FAILURE", "details": errors})
        return errors, original_row_count, original_row_count, None
    if task:
        task.update_state(state="PROGRESS", meta={"step": "Header Validation", "status": "SUCCESS"})
        time.sleep(2)

    df = rename_to_internal(df_read.copy())

    # Row Integrity & Coercion
    if task:
        task.update_state(state="PROGRESS", meta={"step": "Row Integrity & Type Coercion", "status": "IN_PROGRESS"})
    bad_tab_rows = detect_row_length_mismatch(file_bytes)
    if bad_tab_rows:
        errors.setdefault("row_length_mismatch", []).extend(bad_tab_rows)

    df = coerce_types(df)

    parse_loss = find_numeric_parse_loss_rows(df)
    if parse_loss:
        errors.setdefault("parse_errors", []).extend(parse_loss)
    if task:
        task.update_state(state="PROGRESS", meta={"step": "Row Integrity & Type Coercion", "status": "SUCCESS"})
        time.sleep(2)

    # Business Rule Validation
    if task:
        task.update_state(state="PROGRESS", meta={"step": "Business Rule Validation", "status": "IN_PROGRESS"})
    domain_error_rows = validate_business_rules(df)
    if domain_error_rows:
        errors.setdefault("domain_errors", []).extend(domain_error_rows)

    calc_errors = run_calculation_checks(df)
    if calc_errors:
        errors.setdefault("calculation_errors", []).extend(calc_errors)
    if task:
        task.update_state(state="PROGRESS", meta={"step": "Business Rule Validation", "status": "SUCCESS"})
        time.sleep(2)

    bad_rows = get_all_invalid_row_indices(errors)
    problematic_row_count = len(bad_rows)

    return errors, original_row_count, problematic_row_count, df


def process_emex_file(
    file_obj: UploadedFile,
) -> tuple[pd.DataFrame | None, dict[str, list[str | int]], int, int]:
    """
    Orchestrates full processing, including validation and data cleaning.
    """
    errors, original_row_count, problematic_row_count, df = get_validation_summary(file_obj)

    if df is None:
        return None, errors, original_row_count, problematic_row_count

    # Drop invalid rows if any were found
    if problematic_row_count > 0:
        bad_row_indices = sorted(list(get_all_invalid_row_indices(errors)))
        logger.warning("Dropping {} rows due to validation errors: {}", problematic_row_count, bad_row_indices)
        df = df.drop(index=bad_row_indices)

    # Add uploaded_at and finalize columns for insertion
    df["uploaded_at"] = datetime.date.today()
    df = rename_for_clickhouse(df)

    logger.debug("Prepared DataFrame dtypes for ClickHouse:\n{}", df.dtypes)

    return df, errors, original_row_count, problematic_row_count


def insert_data_to_clickhouse(df: pd.DataFrame) -> tuple[bool, str]:
    """
    Inserts a DataFrame into the `sup_stat.emex_dif` table in ClickHouse.
    """
    try:
        with get_clickhouse_client(readonly=0) as client:
            client.insert_df("sup_stat.emex_dif", df)
            return True, f"Successfully inserted {len(df)} rows."
    except Exception as e:
        logger.error("An error occurred with ClickHouse operation: {}", e)
        return False, f"Failed to insert data: {e}"
