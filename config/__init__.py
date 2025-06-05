"""
Config package for the project.

This package contains configuration modules for the project.
"""

# This will make sure the app is always imported when Django starts
from config.third_party_config.celery import app as celery_app

__all__ = ("celery_app",)
