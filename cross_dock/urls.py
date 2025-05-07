from django.urls import path

from . import views

app_name = "cross_dock"
urlpatterns = [
    path("", views.index, name="index"),
]
