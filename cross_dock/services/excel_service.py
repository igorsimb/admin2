"""
Excel service for cross-dock functionality.

This module provides functions for processing cross-dock data and generating Excel files.
"""

import os
import uuid
import logging
import pandas as pd
from typing import Tuple, List, Dict
from django.conf import settings

from common.utils.excel import create_workbook, save_workbook
from cross_dock.services.clickhouse_service import query_supplier_data

logger = logging.getLogger(__name__)


def process_cross_dock_data(data: List[Dict[str, str]], platform: str = "emex") -> Tuple[str, str]:
    """
    Process cross-dock data and generate Excel file.

    Args:
        data: List of dictionaries containing brand and article information
        platform: Platform to query (default: "emex")

    Returns:
        tuple: (progress percentage, file URL)
    """
    logger.info(f"Processing cross-dock data for platform {platform}")

    wb = create_workbook()
    result_sheet = wb.active

    headers = ["SKU", "Бренд", "Артикул", "Лучшая цена 1", "Количество 1", "Название поставщика 1",
               "Лучшая цена 2", "Количество 2", "Название поставщика 2",
               "Лучшая цена 3", "Количество 3", "Название поставщика 3"]

    for col_num, header in enumerate(headers, start=1):
        result_sheet.cell(row=1, column=col_num, value=header)

    total_rows = len(data)
    processed_rows = 0

    for row_num, item in enumerate(data, start=2):
        brand = item['Бренд']
        article = item['Артикул']
        logger.debug(f"Processing row {row_num-1}/{total_rows}: {brand}, {article}")

        sku = f"{brand}|{article}"

        result_sheet.cell(row=row_num, column=1, value=sku)
        result_sheet.cell(row=row_num, column=2, value=brand)
        result_sheet.cell(row=row_num, column=3, value=article)
        try:
            price_results = query_supplier_data(brand, article, platform)

            for i, (_, price_row) in enumerate(price_results.iterrows(), start=0):
                if i < 3:  # Only use the first 3 results
                    price = price_row['price']
                    quantity = price_row['quantity']
                    supplier_name = price_row['supplier_name']

                    col_offset = (i * 3)
                    result_sheet.cell(row=row_num, column=4 + col_offset, value=float(price))
                    result_sheet.cell(row=row_num, column=5 + col_offset, value=int(quantity))
                    result_sheet.cell(row=row_num, column=6 + col_offset, value=str(supplier_name))
            for i in range(len(price_results), 3):
                col_offset = (i * 3)
                result_sheet.cell(row=row_num, column=4 + col_offset, value=None)
                result_sheet.cell(row=row_num, column=5 + col_offset, value=None)
                result_sheet.cell(row=row_num, column=6 + col_offset, value=None)

        except Exception as e:
            logger.error(f"Error processing row {row_num}: {e}")
            # Fill cells with empty values on error
            for i in range(3):
                col_offset = (i * 3)
                result_sheet.cell(row=row_num, column=4 + col_offset, value=None)
                result_sheet.cell(row=row_num, column=5 + col_offset, value=None)
                result_sheet.cell(row=row_num, column=6 + col_offset, value=None)

        processed_rows += 1

    file_name = f"cross_dock_{uuid.uuid4()}.xlsx"
    file_url = save_workbook(wb, file_name)

    progress = "100%"
    return progress, file_url


def process_cross_dock_data_from_file(input_file_path: str, platform: str = "emex") -> str:
    """
    Process cross-dock data from an Excel file and generate a new Excel file.

    Args:
        input_file_path: Path to the input Excel file
        platform: Platform to query (default: "emex")

    Returns:
        str: Path to the generated output file
    """
    logger.info(f"Processing cross-dock data from file {input_file_path}")

    df = pd.read_excel(input_file_path)
    data = df.to_dict('records')

    _, file_url = process_cross_dock_data(data, platform)

    # Extract filename from URL (handle both forward and backslashes)
    file_name = file_url.replace('\\', '/').split('/')[-1]
    output_file_path = os.path.join(settings.MEDIA_ROOT, 'exports', file_name)

    return output_file_path
