from django.contrib import admin

from .models import CrossDockTask


@admin.register(CrossDockTask)
class CrossDockTaskAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "created_at", "updated_at", "filename")
    list_filter = ("status", "created_at")
    search_fields = ("id", "filename", "error_message")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "created_at"

    @admin.action(description="Mark selected tasks as failed")
    def mark_as_failed(self, request, queryset):
        updated_count = 0
        for task in queryset:
            task.mark_as_failed("Marked as failed via admin action")
            updated_count += 1
        self.message_user(request, f"{updated_count} tasks marked as failed.")

    actions = ["mark_as_failed"]
