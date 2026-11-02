from django.urls import path

from apps.accounts.views import (
    GithubConnectStubView,
    LockfileLogoutView,
    ProfileView,
)

app_name = "accounts"

urlpatterns = [
    path("github/", GithubConnectStubView.as_view(), name="github"),
    path("logout/", LockfileLogoutView.as_view(), name="logout"),
    path("profile/", ProfileView.as_view(), name="profile"),
]
