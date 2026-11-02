from django.urls import path

from apps.dashboard.views import DashboardStatsPartialView, DashboardView

app_name = "dashboard"

urlpatterns = [
    path("", DashboardView.as_view(), name="home"),
    path("partials/stats/", DashboardStatsPartialView.as_view(), name="stats_partial"),
]
