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


class Supplier(BaseModel):
    """
    Represents a supplier.
    """

    supid = models.PositiveIntegerField(primary_key=True, help_text="The supplier's unique ID (dif_id from ClickHouse)")
    name = models.CharField(max_length=255)
    is_partner = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} ({self.supid})"
