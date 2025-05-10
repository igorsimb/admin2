"""
Tests for Excel utilities.

This module contains tests for the Excel utility functions that will be used
for creating and saving Excel workbooks.
"""

import os
import tempfile
from unittest import mock

import pytest
from django.conf import settings

# Import will fail until we implement the code
from common.utils.excel import create_workbook, save_workbook


class TestExcelUtilities:
    """Test suite for Excel utility functions."""

    def test_create_workbook(self):
        """Test that create_workbook returns a valid workbook object."""
        # This will fail until we implement create_workbook correctly
        wb = create_workbook()
        assert wb is not None
        assert hasattr(wb, 'active')

    def test_save_workbook(self):
        """Test that save_workbook correctly saves a workbook to a file."""
        # Create a temporary directory for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock settings to use the temp directory
            with mock.patch('django.conf.settings.MEDIA_ROOT', temp_dir):
                with mock.patch('django.conf.settings.MEDIA_URL', '/media/'):
                    # Create a workbook
                    wb = create_workbook()

                    # Save the workbook
                    filename = "test_workbook.xlsx"
                    url = save_workbook(wb, filename)

                    # Check that the file exists
                    file_path = os.path.join(temp_dir, 'exports', filename)
                    assert os.path.exists(file_path)

                    # Check that the URL is correct
                    expected_url = '/media/exports/test_workbook.xlsx'
                    assert url == expected_url
