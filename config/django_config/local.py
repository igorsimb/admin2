"""
Local settings for project config.

This file overrides base.py and is used for the local development environment.
"""

from .base import *  # noqa

DEBUG = env.bool("DJANGO_DEBUG", default=True)
STATICFILES_DIRS = [BASE_DIR / "static"]

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
