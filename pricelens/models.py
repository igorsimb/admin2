from urllib.parse import quote
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models

from common.models import BaseModel, Supplier

User = get_user_model()


class InvestigationStatus(models.IntegerChoices):
    OPEN = 0, "Открыто"
    RESOLVED = 1, "Решено"
    UNRESOLVED = 2, "Не решено"  # noqa


class BucketChoices(models.TextChoices):
    CONSISTENT = "consistent", "Стабильные"
    INCONSISTENT = "inconsistent", "Нестабильные"
    DEAD = "dead", "Мертвые"


class FailReason(BaseModel):
    code = models.CharField(
        max_length=100,
        unique=True,
        help_text="Внутренний код ошибки, напр. 'FILE_READ_ERROR'",
    )
    name = models.CharField(max_length=255, help_text="Удобочитаемое название ошибки, напр. 'Ошибка чтения файла'")
    description = models.TextField(help_text="Подробное описание ошибки")

    def __str__(self):
        return self.name


class Investigation(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    event_dt = models.DateTimeField(db_index=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    fail_reason = models.ForeignKey(FailReason, on_delete=models.SET_NULL, null=True, blank=True)
    stage = models.CharField(max_length=32)  # load_mail / load_ftp / consolidate / airflow
    file_path = models.TextField(blank=True, default="")
    status = models.IntegerField(choices=InvestigationStatus.choices, default=InvestigationStatus.OPEN, db_index=True)
    note = models.TextField(blank=True, default="")
    investigated_at = models.DateTimeField(null=True, blank=True)
    investigator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "event_dt"]),
            models.Index(fields=["supplier", "event_dt"]),
        ]

    @property
    def get_download_url(self) -> str:
        """Constructs the full URL to the source file on the Nginx server."""
        base_url = settings.PRICELENS_FILE_SERVER_URL
        if not base_url or not self.file_path:
            return ""
        # Use quote to handle special characters in file paths
        return f"{base_url.rstrip('/')}/{quote(self.file_path.lstrip('/'))}"


class CadenceDaily(models.Model):
    date = models.DateField(db_index=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    had_file = models.BooleanField(default=False)
    attempts = models.PositiveIntegerField(default=0)
    errors = models.PositiveIntegerField(default=0)
    last_stage = models.CharField(max_length=32, blank=True, default="")

    class Meta:
        unique_together = ("date", "supplier")


class CadenceProfile(BaseModel):
    supplier = models.OneToOneField(Supplier, on_delete=models.CASCADE, primary_key=True)
    median_gap_days = models.PositiveIntegerField()
    sd_gap = models.FloatField()
    days_since_last = models.PositiveIntegerField()
    last_success_date = models.DateField()
    bucket = models.CharField(max_length=16, choices=BucketChoices.choices)
