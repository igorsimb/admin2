# ruff: noqa: F405
"""
Test settings for project config.

This file overrides base.py and is used for the test environment.
"""

from .base import *  # noqa

# Use an in-memory SQLite database for testing
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
