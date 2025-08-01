"""
API URL Configuration for the Pricelens app.
"""

from django.urls import path

from .api import LogEventAPIView

app_name = "pricelens-api"

urlpatterns = [
    path("log_event/", LogEventAPIView.as_view(), name="log-event"),
]
