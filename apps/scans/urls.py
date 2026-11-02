from django.urls import path

from apps.scans.views import ScanDetailView, ScanListView

app_name = "scans"

urlpatterns = [
    path("", ScanListView.as_view(), name="list"),
    path("<int:pk>/", ScanDetailView.as_view(), name="detail"),
]
