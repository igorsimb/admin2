from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from .health import HealthCheckView
from .views import IndexView

urlpatterns = [
    path("", IndexView.as_view(), name="index"),
    path("health/", HealthCheckView.as_view(), name="health-check"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
