"""
Context processors for the core app.

These processors add variables to the template context for all templates.
"""

from django.conf import settings


def environment_settings(request):
    """
    Add environment-related settings to the template context.

    This makes these variables available in all templates.
    """
    return {
        "environment": settings.DJANGO_ENVIRONMENT,
        "CLICKHOUSE_HOST": settings.CLICKHOUSE_HOST,
    }
