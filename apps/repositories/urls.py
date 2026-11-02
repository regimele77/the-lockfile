from django.urls import path

from apps.repositories.views import (
    RepositoryConnectStubView,
    RepositoryDetailView,
    RepositoryListView,
)

app_name = "repositories"

urlpatterns = [
    path("", RepositoryListView.as_view(), name="list"),
    path("connect/", RepositoryConnectStubView.as_view(), name="connect"),
    path("<int:pk>/", RepositoryDetailView.as_view(), name="detail"),
]
