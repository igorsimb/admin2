"""
WSGI config for project_name project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Get the environment name from an environment variable, default to staging
ENVIRONMENT = os.environ.get("DJANGO_ENVIRONMENT", "staging")

# Set the settings module based on the environment
if ENVIRONMENT == "production":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.django_config.production")
else:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.django_config.staging")

application = get_wsgi_application()
