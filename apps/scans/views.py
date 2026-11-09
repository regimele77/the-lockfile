from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, ListView

from apps.accounts.services.access_errors import (
    classify_message,
    github_app_public_url,
    github_installations_settings_url,
)
from apps.accounts.services.installation_tokens import app_credentials_configured
from apps.repositories.models import Repository
from apps.scans.models import Scan
from apps.scans.services.display import scan_ordinal, user_scans_qs
from apps.scans.services.enqueue import ScanStartError, enqueue_scan_for_repository
from apps.scans.services.sanitize import sanitize_error_message


def _ordered_findings(scan: Scan):
    severity_order = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
        "info": 4,
    }
    findings = list(scan.findings.all())
    findings.sort(key=lambda f: (severity_order.get(f.severity, 9), f.title.lower()))
    return findings


class ScanListView(LoginRequiredMixin, ListView):
    model = Scan
    template_name = "scans/list.html"
    context_object_name = "scans"
    paginate_by = 25

    def get_queryset(self):
        return user_scans_qs(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.findings.services.guidance import onboarding_guidance

        context["empty_guidance"] = onboarding_guidance(self.request.user)
        return context


class ScanDetailView(LoginRequiredMixin, DetailView):
    model = Scan
    template_name = "scans/detail.html"
    context_object_name = "scan"

    def get_queryset(self):
        return user_scans_qs(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["scan_findings"] = _ordered_findings(self.object)
        context["scan_number"] = scan_ordinal(self.request.user, self.object)
        context.update(_scan_recovery_context(self.object))
        return context


def _scan_recovery_context(scan: Scan) -> dict:
    """Recovery links for failed scans (no secrets in error_message)."""
    raw = sanitize_error_message(scan.error_message or "")
    guidance = classify_message(raw) if raw else None
    return {
        "safe_error_message": raw,
        "recovery": guidance,
        "permissions_url": github_installations_settings_url(),
        "app_public_url": github_app_public_url(),
    }


class ScanStatusPartialView(LoginRequiredMixin, DetailView):
    """HTMX partial: refresh status while a scan is queued or running."""

    model = Scan
    template_name = "scans/partials/status_panel.html"
    context_object_name = "scan"

    def get_queryset(self):
        repos = Repository.objects.selected_for_user(self.request.user)
        return Scan.objects.filter(repository__in=repos).select_related("repository")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_scan_recovery_context(self.object))
        return context


class ScanFindingsPartialView(LoginRequiredMixin, DetailView):
    """HTMX partial: findings table refreshed when a scan finishes."""

    model = Scan
    template_name = "scans/partials/findings_panel.html"
    context_object_name = "scan"

    def get_queryset(self):
        repos = Repository.objects.selected_for_user(self.request.user)
        return Scan.objects.filter(repository__in=repos).select_related("repository")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["scan_findings"] = _ordered_findings(self.object)
        return context


class ScanStartView(LoginRequiredMixin, View):
    """POST: start a scan for one tracked repository."""

    def post(self, request, pk):
        repo = get_object_or_404(
            Repository.objects.selected_for_user(request.user).select_related(
                "installation"
            ),
            pk=pk,
        )
        if not app_credentials_configured():
            messages.warning(
                request,
                "GitHub App credentials are missing on this host. "
                "Set GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY, then try again. "
                "Next: Account settings.",
            )
            return redirect("repositories:detail", pk=repo.pk)
        if repo.installation_id is None:
            messages.warning(
                request,
                "This repository has no GitHub App installation. "
                "Install the App, refresh repositories, then scan again.",
            )
            return redirect("repositories:detail", pk=repo.pk)

        try:
            scan = enqueue_scan_for_repository(
                repo,
                trigger=Scan.Trigger.MANUAL,
            )
        except ScanStartError as exc:
            messages.warning(request, sanitize_error_message(str(exc)))
            return redirect("repositories:detail", pk=repo.pk)

        messages.success(
            request,
            f"Scan queued for {repo.full_name}.",
        )
        return redirect("scans:detail", pk=scan.pk)


class ScanBulkStartView(LoginRequiredMixin, View):
    """POST: start scans for multiple tracked repos from the repository list."""

    def post(self, request):
        raw_ids = request.POST.getlist("repo_ids")
        started = 0
        skipped = 0

        for value in raw_ids:
            try:
                repo_id = int(value)
            except (TypeError, ValueError):
                continue
            repo = (
                Repository.objects.selected_for_user(request.user)
                .filter(pk=repo_id)
                .first()
            )
            if repo is None:
                continue
            try:
                enqueue_scan_for_repository(
                    repo,
                    trigger=Scan.Trigger.MANUAL,
                )
                started += 1
            except ScanStartError:
                skipped += 1

        if started and not skipped:
            messages.success(
                request,
                f"Queued {started} scan{'s' if started != 1 else ''}.",
            )
        elif started and skipped:
            messages.warning(
                request,
                f"Queued {started}, skipped {skipped} "
                "(already running or not eligible).",
            )
        elif skipped:
            messages.info(
                request,
                "No new scans queued. Selected repos already have an active scan.",
            )
        else:
            messages.info(request, "Select at least one repository to scan.")

        return redirect("scans:list" if started else "repositories:list")
