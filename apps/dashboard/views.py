from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.findings.models import Finding
from apps.repositories.models import Repository
from apps.scans.models import Scan


def _repo_scope(user):
    return Repository.objects.selected_for_user(user)


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        repos = _repo_scope(self.request.user)
        context.update(
            {
                "repo_count": repos.count(),
                "scan_count": Scan.objects.filter(repository__in=repos).count(),
                "finding_count": Finding.objects.filter(
                    scan__repository__in=repos
                ).count(),
                "open_critical": Finding.objects.filter(
                    scan__repository__in=repos,
                    severity=Finding.Severity.CRITICAL,
                ).count(),
                "recent_scans": Scan.objects.filter(repository__in=repos)
                .select_related("repository")
                .order_by("-created_at")[:5],
            }
        )
        return context


class DashboardStatsPartialView(LoginRequiredMixin, TemplateView):
    """HTMX partial: refresh overview counts without a full page reload."""

    template_name = "dashboard/partials/stats.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        repos = _repo_scope(self.request.user)
        context.update(
            {
                "repo_count": repos.count(),
                "scan_count": Scan.objects.filter(repository__in=repos).count(),
                "finding_count": Finding.objects.filter(
                    scan__repository__in=repos
                ).count(),
                "open_critical": Finding.objects.filter(
                    scan__repository__in=repos,
                    severity=Finding.Severity.CRITICAL,
                ).count(),
            }
        )
        return context
