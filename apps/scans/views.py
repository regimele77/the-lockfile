from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, ListView

from apps.repositories.models import Repository
from apps.scans.models import Scan
from apps.scans.services.enqueue import ScanStartError, enqueue_scan_for_repository


class ScanListView(LoginRequiredMixin, ListView):
    model = Scan
    template_name = "scans/list.html"
    context_object_name = "scans"
    paginate_by = 25

    def get_queryset(self):
        repos = Repository.objects.selected_for_user(self.request.user)
        return Scan.objects.filter(repository__in=repos).select_related("repository")


class ScanDetailView(LoginRequiredMixin, DetailView):
    model = Scan
    template_name = "scans/detail.html"
    context_object_name = "scan"

    def get_queryset(self):
        repos = Repository.objects.selected_for_user(self.request.user)
        return Scan.objects.filter(repository__in=repos).select_related("repository")


class ScanStatusPartialView(LoginRequiredMixin, DetailView):
    """HTMX partial: refresh status while a scan is queued or running."""

    model = Scan
    template_name = "scans/partials/status_panel.html"
    context_object_name = "scan"

    def get_queryset(self):
        repos = Repository.objects.selected_for_user(self.request.user)
        return Scan.objects.filter(repository__in=repos).select_related("repository")


class ScanStartView(LoginRequiredMixin, View):
    """POST: start a scan for one tracked repository."""

    def post(self, request, pk):
        repo = get_object_or_404(
            Repository.objects.selected_for_user(request.user).select_related(
                "installation"
            ),
            pk=pk,
        )
        try:
            scan = enqueue_scan_for_repository(
                repo,
                trigger=Scan.Trigger.MANUAL,
            )
        except ScanStartError as exc:
            messages.warning(request, str(exc))
            return redirect("repositories:detail", pk=repo.pk)

        messages.success(
            request,
            f"Scan #{scan.pk} queued for {repo.full_name}.",
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
