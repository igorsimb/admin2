"""Read cross-dock input files and export up to three supplier offers per row.

Reports fail on query or export errors so incomplete output is not presented as a
successful report. Both modes normalize uploaded pairs and share offer-selection rules.
"""

import logging
import os
import uuid
from contextlib import nullcontext

import pandas as pd
from django.conf import settings

from common.utils.excel import create_workbook, save_workbook
from cross_dock.services.clickhouse_service import query_supplier_data_mv, supplier_query_session
from cross_dock.services.normalization import normalize_brand_sku_pairs

logger = logging.getLogger(__name__)


def process_cross_dock_data(data: list[dict[str, str]], supplier_list: str, use_mv: bool = False) -> tuple[str, str]:
    """
    Process cross-dock data and generate Excel file.

    Args:
        data: List of dictionaries containing brand and article information
        supplier_list: Supplier list to query (e.g., 'Группа для проценки ТРЕШКА', 'ОПТ-2')
        use_mv: Whether to use the MV-based query (default: False)

    Returns:
        tuple: (progress percentage, file URL)
    """
    logger.info(f"Processing cross-dock data for supplier list {supplier_list} (use_mv={use_mv})")
    logger.info(f"Received {len(data)} records to process")

    # Log a sample of the data
    if data:
        sample = data[0]
        logger.debug(f"Sample record: {sample}")

    wb = create_workbook()
    result_sheet = wb.active

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
        result_sheet.cell(row=1, column=col_num, value=header)

    original_pairs = [(str(item["Бренд"]), str(item["Артикул"])) for item in data]
    normalized_pairs = normalize_brand_sku_pairs(original_pairs)
    batch_lookup = {}
    if use_mv:
        batch_df = query_supplier_data_mv(sorted(set(normalized_pairs)), supplier_list)
        for row in batch_df.to_dict("records"):
            batch_lookup.setdefault((row["brand"], row["sku"]), []).append(row)

    with nullcontext() if use_mv else supplier_query_session(supplier_list) as query_supplier:
        for row_num, (original, normalized) in enumerate(zip(original_pairs, normalized_pairs, strict=True), start=2):
            brand, article = original
            result_sheet.cell(row=row_num, column=1, value=f"{brand}|{article}")
            result_sheet.cell(row=row_num, column=2, value=brand)
            result_sheet.cell(row=row_num, column=3, value=article)
            try:
                price_rows = (
                    batch_lookup.get(normalized, []) if use_mv else query_supplier(*normalized).to_dict("records")
                )
                for i, price_row in enumerate(price_rows[:3]):
                    col_offset = i * 3
                    result_sheet.cell(row=row_num, column=4 + col_offset, value=float(price_row["price"]))
                    quantity = price_row["quantity"]
                    safe_qty = int(quantity) if pd.notna(quantity) else None
                    result_sheet.cell(row=row_num, column=5 + col_offset, value=safe_qty)
                    result_sheet.cell(row=row_num, column=6 + col_offset, value=str(price_row["supplier_name"]))
                for i in range(len(price_rows), 3):
                    for column in range(4 + i * 3, 7 + i * 3):
                        result_sheet.cell(row=row_num, column=column, value=None)
            except Exception:
                logger.exception("Error processing cross-dock row %s", row_num)
                raise

    file_name = f"cross_dock_{uuid.uuid4()}.xlsx"
    logger.info(f"Saving workbook as {file_name}")
    file_url = save_workbook(wb, file_name)
    logger.info(f"Workbook saved successfully, URL: {file_url}")

    progress = "100%"
    logger.info("Summary: Processed %s rows.", len(data))
    return progress, file_url


def process_cross_dock_data_from_file(input_file_path: str, supplier_list: str, use_mv: bool = False) -> str:
    """
    Process cross-dock data from an Excel file and generate a new Excel file.

    Args:
        input_file_path: Path to the input Excel file
        supplier_list: Supplier list to query (e.g., 'Группа для проценки ТРЕШКА', 'ОПТ-2')
        use_mv: Whether to use the MV-based query (default: False)

    Returns:
        str: Path to the generated output file
    """
    logger.info(f"Processing cross-dock data from file {input_file_path} (use_mv={use_mv})")

    # Read the Excel file
    try:
        df = pd.read_excel(input_file_path, dtype=str, keep_default_na=False)
        logger.info(f"Excel file read successfully. Columns: {df.columns.tolist()}")
        logger.info(f"First few rows: \n{df.head()}")

        # Check if the required columns exist
        required_columns = ["Бренд", "Артикул"]
        missing_columns = [col for col in required_columns if col not in df.columns]

        if missing_columns:
            # Try to map common column names to the required ones
            column_mapping = {"A": "Бренд", "B": "Артикул", "Brand": "Бренд", "Article": "Артикул", "SKU": "Артикул"}

            # Check if we have unnamed columns (Excel might use them)
            unnamed_columns = [col for col in df.columns if "Unnamed" in str(col)]
            if len(unnamed_columns) >= 2 and missing_columns:
                # Assume first column is Brand and second is Article
                df = df.rename(columns={unnamed_columns[0]: "Бренд", unnamed_columns[1]: "Артикул"})
                logger.info("Renamed unnamed columns to required columns")
                missing_columns = [col for col in required_columns if col not in df.columns]

            # Try standard column mapping
            for old_col, new_col in column_mapping.items():
                if old_col in df.columns and new_col in missing_columns:
                    df = df.rename(columns={old_col: new_col})
                    logger.info(f"Renamed column '{old_col}' to '{new_col}'")
                    missing_columns.remove(new_col)

            # If we still have missing columns, try to infer from the data
            if missing_columns and len(df.columns) >= 2:
                # Assume first column is Brand and second is Article
                column_names = df.columns.tolist()
                if "Бренд" not in df.columns and column_names:
                    df = df.rename(columns={column_names[0]: "Бренд"})
                    logger.info("Inferred first column as Brand")
                if "Артикул" not in df.columns and len(column_names) > 1:
                    df = df.rename(columns={column_names[1]: "Артикул"})
                    logger.info("Inferred second column as Article")
                missing_columns = [col for col in required_columns if col not in df.columns]

            # If we still have missing columns, raise an error
            if missing_columns:
                error_msg = f"Missing required columns: {missing_columns}. Available columns: {df.columns.tolist()}"
                logger.error(error_msg)
                raise ValueError(error_msg)

        # Convert DataFrame to list of dictionaries
        data = df.to_dict("records")
        logger.info(f"Converted DataFrame to {len(data)} records")
    except Exception as e:
        logger.exception(f"Error processing Excel file: {e}")
        raise

    # Process the data
    logger.info(f"Starting to process data with supplier list: {supplier_list}")
    _, file_url = process_cross_dock_data(data, supplier_list, use_mv=use_mv)
    logger.info(f"Data processed successfully, file URL: {file_url}")

    # Extract filename from URL (handle both forward and backslashes)
    file_name = file_url.replace("\\", "/").split("/")[-1]
    output_file_path = os.path.join(settings.MEDIA_ROOT, "exports", file_name)
    logger.info(f"Output file path: {output_file_path}")

    return output_file_path
