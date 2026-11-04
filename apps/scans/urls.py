from django.urls import path

from apps.scans.views import (
    ScanBulkStartView,
    ScanDetailView,
    ScanFindingsPartialView,
    ScanListView,
    ScanStatusPartialView,
)

app_name = "scans"

urlpatterns = [
    path("", ScanListView.as_view(), name="list"),
    path("start-bulk/", ScanBulkStartView.as_view(), name="start_bulk"),
    path("<int:pk>/", ScanDetailView.as_view(), name="detail"),
    path("<int:pk>/status/", ScanStatusPartialView.as_view(), name="status_partial"),
    path(
        "<int:pk>/findings/",
        ScanFindingsPartialView.as_view(),
        name="findings_partial",
    ),
]
