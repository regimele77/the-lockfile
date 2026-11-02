from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LogoutView
from django.urls import reverse_lazy
from django.views.generic import TemplateView


class GithubConnectStubView(TemplateView):
    """Placeholder until GitHub App OAuth / installation is wired up."""

    template_name = "accounts/github.html"


class LockfileLogoutView(LogoutView):
    next_page = reverse_lazy("core:landing")


class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/profile.html"
