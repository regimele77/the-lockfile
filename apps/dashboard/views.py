from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.findings.models import Finding
from apps.repositories.models import Repository
from apps.scans.models import Scan


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "repo_count": Repository.objects.count(),
                "scan_count": Scan.objects.count(),
                "finding_count": Finding.objects.count(),
                "open_critical": Finding.objects.filter(severity=Finding.Severity.CRITICAL).count(),
                "recent_scans": Scan.objects.select_related("repository").order_by("-created_at")[:5],
            }
        )
        return context


class DashboardStatsPartialView(LoginRequiredMixin, TemplateView):
    """HTMX partial: refresh overview counts without a full page reload."""

    template_name = "dashboard/partials/stats.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "repo_count": Repository.objects.count(),
                "scan_count": Scan.objects.count(),
                "finding_count": Finding.objects.count(),
                "open_critical": Finding.objects.filter(severity=Finding.Severity.CRITICAL).count(),
            }
        )
        return context
