import uuid
from typing import ClassVar

from django.conf import settings
from django.db import models
from django.utils import timezone


class CrossDockTask(models.Model):
    """Model for tracking cross-dock tasks."""

    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("PENDING", "Pending"),
        ("RUNNING", "Running"),
        ("SUCCESS", "Success"),
        ("FAILURE", "Failure"),
    ]

    SUPPLIER_GROUP_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("Группа для проценки ТРЕШКА", "Группа для проценки ТРЕШКА"),
        ("ОПТ-2", "ОПТ-2"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    result_url = models.URLField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    # Supplier group selection
    supplier_group = models.CharField(
        max_length=255,
        choices=SUPPLIER_GROUP_CHOICES,
        null=True,
        blank=True,
        help_text="Supplier group used for this task",
    )

    # Input file name
    filename = models.CharField(max_length=255, null=True, blank=True)

    # User who created the task
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cross_dock_tasks",
        help_text="User who created this task",
    )

    def __str__(self):
        return f"CrossDockTask {self.id} - {self.status}"

    def mark_as_running(self):
        """Mark the task as running."""
        self.status = "RUNNING"
        self.save(update_fields=["status", "updated_at"])

    def mark_as_success(self, result_url):
        """Mark the task as successful with its result URL."""
        self.status = "SUCCESS"
        self.result_url = result_url
        self.save(update_fields=["status", "result_url", "updated_at"])

    def mark_as_failed(self, error_message):
        """Mark the task as failed with an error message."""
        self.status = "FAILURE"
        self.error_message = error_message
        self.save(update_fields=["status", "error_message", "updated_at"])

    @property
    def execution_time(self):
        """
        Calculate and format execution time as hours, minutes, seconds.

        Returns:
            str: Formatted execution time (e.g., "2 ч. 30 мин. 15 сек.")
        """
        if self.status in ["SUCCESS", "FAILURE"]:
            seconds = (self.updated_at - self.created_at).total_seconds()
        else:
            seconds = (timezone.now() - self.created_at).total_seconds()

        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        # Format the time string based on duration
        if hours >= 1:
            return f"{int(hours)} ч. {int(minutes)} мин. {int(seconds)} сек."
        elif minutes >= 1:
            return f"{int(minutes)} мин. {int(seconds)} сек."
        else:
            return f"{int(seconds)} сек."

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["supplier_group"]),
        ]
