from django.urls import path

from apps.core.views import (
    HealthPageView,
    LandingView,
    PrivacyView,
    TermsView,
    healthcheck,
)

app_name = "core"

urlpatterns = [
    path("", LandingView.as_view(), name="landing"),
    path("health/", healthcheck, name="healthcheck"),
    path("status/", HealthPageView.as_view(), name="status"),
    path("privacy/", PrivacyView.as_view(), name="privacy"),
    path("terms/", TermsView.as_view(), name="terms"),
]
