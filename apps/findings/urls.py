from django.urls import path

from apps.findings.views import (
    FindingDetailView,
    FindingListView,
    FindingStatusUpdateView,
)

app_name = "findings"

urlpatterns = [
    path("", FindingListView.as_view(), name="list"),
    path("<int:pk>/", FindingDetailView.as_view(), name="detail"),
    path("<int:pk>/status/", FindingStatusUpdateView.as_view(), name="status"),
]
