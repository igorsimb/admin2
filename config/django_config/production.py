# ruff: noqa: F405
"""
Production settings for project config.

This file overrides base.py and is used for the production environment.
"""

import os

from .base import *  # noqa

env.read_env(BASE_DIR / ".env.prod")

DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"])
STATICFILES_DIRS = [BASE_DIR / "static"]

# SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365  # 1 year
# SECURE_SSL_REDIRECT = True
# SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# SESSION_COOKIE_SECURE = True
# CSRF_COOKIE_SECURE = True
# SECURE_HSTS_PRELOAD = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.{}".format(os.getenv("POSTGRES_ENGINE", "postgresql")),
        "NAME": os.getenv("POSTGRES_DB", "polls"),
        "USER": os.getenv("POSTGRES_USER", "myprojectuser"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "password"),
        "HOST": os.getenv("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.getenv("POSTGRES_PORT", 5432),
    }
}

STATIC_ROOT = BASE_DIR / "staticfiles"
