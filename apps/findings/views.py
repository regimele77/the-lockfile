from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, ListView

from apps.findings.models import Finding
from apps.findings.services.guidance import onboarding_guidance
from apps.repositories.models import Repository
from apps.scans.models import Scan


def _user_findings_qs(user):
    repos = Repository.objects.selected_for_user(user)
    return Finding.objects.filter(scan__repository__in=repos).select_related(
        "scan", "scan__repository"
    )


class FindingListView(LoginRequiredMixin, ListView):
    model = Finding
    template_name = "findings/list.html"
    context_object_name = "findings"
    paginate_by = 25

    def get_queryset(self):
        qs = _user_findings_qs(self.request.user)

        status = self.request.GET.get("status", "open").lower()
        if status == "all":
            pass
        elif status in Finding.Status.values:
            qs = qs.filter(status=status)
        else:
            qs = qs.filter(status=Finding.Status.OPEN)
            status = "open"

        severity = self.request.GET.get("severity", "").lower()
        if severity in Finding.Severity.values:
            qs = qs.filter(severity=severity)

        category = self.request.GET.get("category", "").lower()
        if category in Finding.Category.values:
            qs = qs.filter(category=category)

        repo_id = self.request.GET.get("repository", "").strip()
        if repo_id.isdigit():
            qs = qs.filter(scan__repository_id=int(repo_id))

        scan_id = self.request.GET.get("scan", "").strip()
        if scan_id.isdigit():
            qs = qs.filter(scan_id=int(scan_id))

        return qs

    def get_template_names(self):
        if self.request.htmx:
            return ["findings/partials/filtered.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        request = self.request
        repos = Repository.objects.selected_for_user(request.user).order_by("full_name")

        status = request.GET.get("status", "open").lower()
        if status not in {"all", *Finding.Status.values}:
            status = "open"

        severity = request.GET.get("severity", "").lower()
        if severity not in Finding.Severity.values:
            severity = ""

        category = request.GET.get("category", "").lower()
        if category not in Finding.Category.values:
            category = ""

        repository = request.GET.get("repository", "").strip()
        if not repository.isdigit():
            repository = ""

        scan = request.GET.get("scan", "").strip()
        if not scan.isdigit():
            scan = ""

        filters_active = bool(severity or category or repository or scan or status != "open")

        context.update(
            {
                "active_status": status,
                "active_severity": severity,
                "active_category": category,
                "active_repository": repository,
                "active_scan": scan,
                "status_choices": Finding.Status.choices,
                "severity_choices": Finding.Severity.choices,
                "category_choices": Finding.Category.choices,
                "filter_repositories": repos,
                "filter_scans": (
                    Scan.objects.filter(repository__in=repos)
                    .select_related("repository")
                    .order_by("-created_at", "-pk")[:50]
                ),
                "filters_active": filters_active,
                "empty_guidance": onboarding_guidance(request.user),
            }
        )
        return context


class FindingDetailView(LoginRequiredMixin, DetailView):
    model = Finding
    template_name = "findings/detail.html"
    context_object_name = "finding"

    def get_queryset(self):
        return _user_findings_qs(self.request.user)


class FindingStatusUpdateView(LoginRequiredMixin, View):
    """POST: mark a finding open, resolved, or ignored within the user scope."""

    _ACTIONS = {
        "resolve": Finding.Status.RESOLVED,
        "ignore": Finding.Status.IGNORED,
        "reopen": Finding.Status.OPEN,
    }

    def post(self, request, pk):
        finding = get_object_or_404(_user_findings_qs(request.user), pk=pk)
        action = (request.POST.get("action") or "").strip().lower()
        new_status = self._ACTIONS.get(action)
        if new_status is None:
            messages.error(request, "Unknown status action.")
            return redirect("findings:detail", pk=finding.pk)

        if finding.status != new_status:
            finding.status = new_status
            finding.save(update_fields=["status"])
            messages.success(
                request,
                f"Finding marked {finding.get_status_display().lower()}.",
            )

        next_url = (request.POST.get("next") or "").strip()
        if next_url.startswith("/findings/") and "://" not in next_url:
            return redirect(next_url)
        return redirect("findings:detail", pk=finding.pk)
