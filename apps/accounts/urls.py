from django.urls import path

from apps.accounts.views import (
    GithubConnectView,
    GithubInstallStartView,
    GithubOAuthCallbackView,
    GithubOAuthStartView,
    GithubSetupCallbackView,
    LockfileLogoutView,
    ProfileView,
)
from apps.accounts.webhook_views import GithubWebhookView

app_name = "accounts"

urlpatterns = [
    path("profile/", ProfileView.as_view(), name="profile"),
    path("github/", GithubConnectView.as_view(), name="github"),
    path("github/start/", GithubOAuthStartView.as_view(), name="github_start"),
    path("github/callback/", GithubOAuthCallbackView.as_view(), name="github_callback"),
    path("github/setup/", GithubSetupCallbackView.as_view(), name="github_setup"),
    path("github/install/", GithubInstallStartView.as_view(), name="github_install"),
    path("github/webhook/", GithubWebhookView.as_view(), name="github_webhook"),
    path("logout/", LockfileLogoutView.as_view(), name="logout"),
]
