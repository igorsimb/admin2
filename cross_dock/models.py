import uuid
from typing import ClassVar

from django.db import models


class CrossDockTask(models.Model):
    """Model for tracking cross-dock tasks."""

    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("PENDING", "Pending"),
        ("RUNNING", "Running"),
        ("SUCCESS", "Success"),
        ("FAILURE", "Failure"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    result_url = models.URLField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    # Expected format: {"brands": [...], "articles": [...], "region": "...", ...}
    input_data = models.JSONField(default=dict)

    # Expected format: {"emex": true, "autopiter": true, "exist": false, ...}
    platforms = models.JSONField(default=dict)

    filename = models.CharField(max_length=255, null=True, blank=True)

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

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]
