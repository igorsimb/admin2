from django.contrib import admin

from .models import CadenceProfile, Investigation


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
