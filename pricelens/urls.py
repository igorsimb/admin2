from django.urls import path

from . import views

app_name = "pricelens"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("queue/", views.QueueView.as_view(), name="queue"),
    path("cadence/", views.CadenceView.as_view(), name="cadence"),
    path("investigate/<uuid:pk>/", views.InvestigationDetailView.as_view(), name="investigate"),
]
