from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts.models import Profile, User


class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ["email", "username", "is_superuser"]


admin.site.register(User, CustomUserAdmin)
admin.site.register(Profile)
