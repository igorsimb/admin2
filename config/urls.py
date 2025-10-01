from allauth.account.models import EmailAddress
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sites.models import Site
from django.urls import include, path

from accounts.views import profile_view

urlpatterns = [
    # Django admin
    path("admin/", admin.site.urls),
    # User management
    path("accounts/", include("allauth.urls")),
    path("profile/", include("accounts.urls")),
    path("@<username>/", profile_view, name="profile"),
    # Local apps
    path("", include("core.urls")),
    path("cross-dock/", include("cross_dock.urls")),
    path("pricelens/", include("pricelens.urls")),
    path("api/v1/pricelens/", include("pricelens.urls_api")),
    path("emex-upload/", include("emex_upload.urls")),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.unregister(Site)
admin.site.unregister(EmailAddress)
