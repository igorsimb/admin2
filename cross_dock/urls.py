from django.urls import path

from . import views

app_name = "cross_dock"
urlpatterns = [
    path("", views.index, name="index"),
    path("process/", views.process_file, name="process_file"),
    path("tasks/", views.CrossDockTaskListView.as_view(), name="task_list"),
]
