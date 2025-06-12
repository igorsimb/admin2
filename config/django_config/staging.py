# ruff: noqa: F405
"""
Staging settings for project config.

This file overrides base.py and is used for the staging/development environment.
"""

from .base import *  # noqa

env.read_env(BASE_DIR / ".env.staging")

DEBUG = env.bool("DJANGO_DEBUG", default=True)
STATICFILES_DIRS = [BASE_DIR / "static"]

INSTALLED_APPS += [
    "django_extensions",
]


DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
