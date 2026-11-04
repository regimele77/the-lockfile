from django.urls import path

from apps.repositories.views import (
    RepositoryConnectView,
    RepositoryDetailView,
    RepositoryListView,
)
from apps.scans.views import ScanStartView

app_name = "repositories"

urlpatterns = [
    path("", RepositoryListView.as_view(), name="list"),
    path("connect/", RepositoryConnectView.as_view(), name="connect"),
    path("<int:pk>/", RepositoryDetailView.as_view(), name="detail"),
    path("<int:pk>/scan/", ScanStartView.as_view(), name="scan_start"),
]
