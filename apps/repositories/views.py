from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView, ListView, TemplateView

from apps.repositories.models import Repository


class RepositoryListView(LoginRequiredMixin, ListView):
    model = Repository
    template_name = "repositories/list.html"
    context_object_name = "repositories"
    paginate_by = 25


class RepositoryDetailView(LoginRequiredMixin, DetailView):
    model = Repository
    template_name = "repositories/detail.html"
    context_object_name = "repository"


class RepositoryConnectStubView(LoginRequiredMixin, TemplateView):
    template_name = "repositories/connect.html"
