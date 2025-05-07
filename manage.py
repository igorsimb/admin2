#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys


def main():
    """Run administrative tasks."""
    # Get the environment name from an environment variable, default to staging
    environment = os.environ.get("DJANGO_ENVIRONMENT", "staging")
    print(f"Using {environment} environment")

    # Set the settings module based on the environment
    if environment == "production":
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.django_config.production")
    else:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.django_config.staging")

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
