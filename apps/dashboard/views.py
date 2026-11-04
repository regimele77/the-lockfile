from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.findings.models import Finding
from apps.findings.services.guidance import onboarding_guidance
from apps.repositories.models import Repository
from apps.scans.models import Scan


def _repo_scope(user):
    return Repository.objects.selected_for_user(user)


def _dashboard_counts(user):
    repos = _repo_scope(user)
    open_findings = Finding.objects.filter(
        scan__repository__in=repos,
        status=Finding.Status.OPEN,
    )
    return {
        "repo_count": repos.count(),
        "scan_count": Scan.objects.filter(repository__in=repos).count(),
        "finding_count": open_findings.count(),
        "open_critical": open_findings.filter(
            severity=Finding.Severity.CRITICAL,
        ).count(),
    }


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        repos = _repo_scope(self.request.user)
        guidance = onboarding_guidance(self.request.user)
        context.update(_dashboard_counts(self.request.user))
        context.update(
            {
                "recent_scans": Scan.objects.filter(repository__in=repos)
                .select_related("repository")
                .order_by("-created_at", "-pk")[:5],
                "guidance": guidance,
                "show_next_step": guidance.stage
                in {
                    "no_installation",
                    "no_repos",
                    "no_scans",
                    "no_open_findings",
                },
            }
        )
        return context


class DashboardStatsPartialView(LoginRequiredMixin, TemplateView):
    """HTMX partial: refresh overview counts without a full page reload."""

    template_name = "dashboard/partials/stats.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_dashboard_counts(self.request.user))
        return context
