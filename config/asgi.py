"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

# Get the environment name from an environment variable, default to staging
ENVIRONMENT = os.environ.get("DJANGO_ENVIRONMENT", "staging")

# Set the settings module based on the environment
if ENVIRONMENT == "production":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.django_config.production")
else:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.django_config.staging")

application = get_asgi_application()
