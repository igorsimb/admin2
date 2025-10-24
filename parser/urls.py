from django.urls import path
from . import views

app_name = "parser"

urlpatterns = [
    path("", views.upload_file_view, name="upload"),
    path("task-status/<str:task_id>/", views.task_status_view, name="task_status"),
]