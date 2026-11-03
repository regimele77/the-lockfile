from django.urls import path

from apps.repositories.views import (
    RepositoryConnectView,
    RepositoryDetailView,
    RepositoryListView,
)

app_name = "repositories"

urlpatterns = [
    path("", RepositoryListView.as_view(), name="list"),
    path("connect/", RepositoryConnectView.as_view(), name="connect"),
    path("<int:pk>/", RepositoryDetailView.as_view(), name="detail"),
]
