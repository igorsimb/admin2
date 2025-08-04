from django.contrib import admin, messages
from django.utils import timezone

from .models import CadenceProfile, Investigation, InvestigationStatus


@admin.register(Investigation)
class InvestigationAdmin(admin.ModelAdmin):
    list_display = (
        "event_dt",
        "supplier",
        "error_text",
        "status",
        "investigator",
        "stage",
        "note",
    )
    list_filter = ("status", "stage", "event_dt", "investigator")
    search_fields = ("supplier__supid", "supplier__name", "error_text", "note", "investigator__username")
    search_help_text = "supid, supplier name, error_text, note, username"
    readonly_fields = ("created_at", "investigated_at")
    list_per_page = 50
    actions = ["mark_resolved", "mark_open"]

    @admin.action(description="Mark selected investigations as Resolved")
    def mark_resolved(self, request, queryset):
        updated_count = queryset.update(
            status=InvestigationStatus.RESOLVED,
            investigator=request.user,
            investigated_at=timezone.now(),
        )
        self.message_user(
            request,
            f"{updated_count} investigations were successfully marked as resolved.",
            messages.SUCCESS,
        )

    @admin.action(description="Mark selected investigations as Open")
    def mark_open(self, request, queryset):
        updated_count = queryset.update(
            status=InvestigationStatus.OPEN,
            investigator=None,
            investigated_at=None,
        )
        self.message_user(
            request,
            f"{updated_count} investigations were successfully marked as open.",
            messages.SUCCESS,
        )


@admin.register(CadenceProfile)
class CadenceProfileAdmin(admin.ModelAdmin):
    """
    Read-only admin view for CadenceProfile, as it is populated by a Celery task.
    """

    list_display = (
        "supplier",
        "bucket",
        "median_gap_days",
        "sd_gap",
        "days_since_last",
        "last_success_date",
        "updated_at",
    )
    list_filter = ("bucket",)
    search_fields = ("supplier__supid", "supplier__name")

    # def has_add_permission(self, request):
    #     return False
    #
    # def has_change_permission(self, request, obj=None):
    #     return False
    #
    # def has_delete_permission(self, request, obj=None):
    #     return False
