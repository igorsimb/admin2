"""
Excel utilities.

This module provides utility functions for creating and saving Excel workbooks.
"""

import logging
import os

from django.conf import settings
from openpyxl import Workbook

logger = logging.getLogger(__name__)


def create_workbook():
    """
    Create a new Excel workbook.

    Returns:
        Workbook: A new Excel workbook
    """
    return Workbook()


def save_workbook(wb: Workbook, filename: str) -> str:
    """
    Save workbook to the exports directory.

    Args:
        wb: The workbook to save
        filename: The filename to save as

    Returns:
        str: The URL to the saved file
    """
    if not wb:
        raise ValueError("Workbook cannot be None")
    if not filename:
        raise ValueError("Filename cannot be empty")

    filename = os.path.basename(filename)
    export_dir = os.path.join(settings.MEDIA_ROOT, "exports")
    os.makedirs(export_dir, exist_ok=True)

    file_path = os.path.join(export_dir, filename)
    wb.save(file_path)

    # Ensure forward slashes for URLs regardless of OS
    url = f"{settings.MEDIA_URL}exports/{filename}"
    url = url.replace("\\", "/")
    logger.info(f"Saved workbook to {file_path}, URL: {url}")
    return url
