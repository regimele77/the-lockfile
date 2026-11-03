from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.views.generic import DetailView, ListView, TemplateView

from apps.accounts.models import GitHubInstallation
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


class RepositoryConnectView(LoginRequiredMixin, TemplateView):
    template_name = "repositories/connect.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["installations"] = GitHubInstallation.objects.filter(
            user=self.request.user
        )
        context["install_url"] = reverse("accounts:github_install")
        return context
