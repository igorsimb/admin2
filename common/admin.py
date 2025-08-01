from django.contrib import admin

from .models import Supplier


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("supid", "name", "is_partner")
    search_fields = (
        "supid",
        "name",
    )
