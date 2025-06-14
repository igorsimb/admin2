from django.urls import path

from .views import (
    email_change_view,
    email_verify,
    profile_delete_view,
    profile_edit_view,
    profile_settings_view,
    profile_view,
)

urlpatterns = [
    path("", profile_view, name="profile"),
    path("edit/", profile_edit_view, name="profile_edit"),
    path("onboarding/", profile_edit_view, name="profile_onboarding"),
    path("settings/", profile_settings_view, name="profile_settings"),
    path("email-change/", email_change_view, name="email_change"),
    path("email-verify/", email_verify, name="email_verify"),
    path("delete/", profile_delete_view, name="profile_delete"),
]
