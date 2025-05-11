"""
Tests for Excel utilities.

This module contains tests for the Excel utility functions that will be used
for creating and saving Excel workbooks.
"""

import os
import tempfile
from unittest import mock

from common.utils.excel import create_workbook, save_workbook


class TestExcelUtilities:
    """Test suite for Excel utility functions."""

    def test_create_workbook(self):
        """Test that create_workbook returns a valid workbook object."""
        wb = create_workbook()
        assert wb is not None
        assert hasattr(wb, "active")

    def test_save_workbook(self):
        """Test that save_workbook correctly saves a workbook to a file."""
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch("django.conf.settings.MEDIA_ROOT", temp_dir),
            mock.patch("django.conf.settings.MEDIA_URL", "/media/"),
        ):
            wb = create_workbook()
            filename = "test_workbook.xlsx"
            url = save_workbook(wb, filename)
            file_path = os.path.join(temp_dir, "exports", filename)
            assert os.path.exists(file_path)
            # Verify the file is a valid Excel file
            assert os.path.getsize(file_path) > 0
            # Verify workbook can be reopened
            from openpyxl import load_workbook

            reopened_wb = load_workbook(file_path)
            assert reopened_wb is not None
            expected_url = "/media/exports/test_workbook.xlsx"
            assert url == expected_url
