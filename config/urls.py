from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("repositories/", include("apps.repositories.urls")),
    path("scans/", include("apps.scans.urls")),
    path("findings/", include("apps.findings.urls")),
]
