"""
Common models for the project.

This module contains common models that can be used across the project.
"""

from django.db import models
from django.utils import timezone


class BaseModel(models.Model):
    """
    Base model with created_at and updated_at fields.

    This abstract model can be inherited by other models to add
    created_at and updated_at fields automatically.
    """

    created_at = models.DateTimeField(db_index=True, default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
