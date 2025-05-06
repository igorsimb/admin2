"""
Production settings for project config.

This file overrides base.py and is used for the production environment.
"""

from .base import *  # noqa

DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365  # 1 year
SECURE_SSL_REDIRECT = True
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_PRELOAD = True
