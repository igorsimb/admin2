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
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch("django.conf.settings.MEDIA_ROOT", temp_dir):
                with mock.patch("django.conf.settings.MEDIA_URL", "/media/"):
                    wb = create_workbook()
                    filename = "test_workbook.xlsx"
                    url = save_workbook(wb, filename)

                    file_path = os.path.join(temp_dir, "exports", filename)
                    assert os.path.exists(file_path)

                    expected_url = "/media/exports/test_workbook.xlsx"
                    assert url == expected_url
