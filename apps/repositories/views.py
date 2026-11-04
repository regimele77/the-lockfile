from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import DetailView, ListView, TemplateView

from apps.accounts.models import GitHubInstallation
from apps.accounts.services.github import GitHubAppError
from apps.accounts.services.installation_tokens import app_credentials_configured
from apps.repositories.models import Repository
from apps.repositories.services.sync import (
    sync_repositories_for_user,
    update_repository_selection,
)


class RepositoryListView(LoginRequiredMixin, ListView):
    model = Repository
    template_name = "repositories/list.html"
    context_object_name = "repositories"
    paginate_by = 25

    def get_queryset(self):
        return (
            Repository.objects.selected_for_user(self.request.user)
            .select_related("installation")
            .order_by("full_name")
        )


class RepositoryDetailView(LoginRequiredMixin, DetailView):
    model = Repository
    template_name = "repositories/detail.html"
    context_object_name = "repository"

    def get_queryset(self):
        return Repository.objects.selected_for_user(self.request.user).select_related(
            "installation"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.scans.models import Scan
        from apps.scans.services.enqueue import repository_has_active_scan

        repo = self.object
        context["recent_scans"] = (
            Scan.objects.filter(repository=repo)
            .order_by("-created_at")[:10]
        )
        context["scan_in_progress"] = repository_has_active_scan(repo)
        return context


class RepositoryConnectView(LoginRequiredMixin, TemplateView):
    """
    Choose which installed repositories to track.

    GET: show installations and synced repos with selection state.
    POST action=refresh: re-sync from GitHub.
    POST action=save: persist checkbox selection.
    """

    template_name = "repositories/connect.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        installations = list(
            GitHubInstallation.objects.filter(user=self.request.user).order_by(
                "account_login"
            )
        )
        repositories = list(
            Repository.objects.for_user(self.request.user)
            .select_related("installation")
            .order_by("full_name")
        )
        selected_count = sum(1 for r in repositories if r.is_selected)
        context.update(
            {
                "installations": installations,
                "repositories": repositories,
                "selected_count": selected_count,
                "install_url": reverse("accounts:github_install"),
                "app_credentials_ready": app_credentials_configured(),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "save")

        if action == "refresh":
            return self._handle_refresh(request)
        if action == "save":
            return self._handle_save(request)

        messages.error(request, "Unknown action.")
        return redirect("repositories:connect")

    def _handle_refresh(self, request):
        if not GitHubInstallation.objects.filter(user=request.user).exists():
            messages.warning(
                request,
                "Install the GitHub App before refreshing repositories.",
            )
            return redirect("repositories:connect")

        if not app_credentials_configured():
            messages.error(
                request,
                "Set GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY (or path) to sync repos.",
            )
            return redirect("repositories:connect")

        try:
            result = sync_repositories_for_user(request.user)
        except GitHubAppError as exc:
            messages.error(request, str(exc))
            return redirect("repositories:connect")

        if result.errors:
            for err in result.errors:
                messages.error(request, err)
            if result.upserted:
                messages.warning(
                    request,
                    f"Partial sync: {result.upserted} repos updated, "
                    f"{result.removed} removed.",
                )
        else:
            messages.success(
                request,
                f"Synced {result.upserted} repositories from GitHub"
                + (f" ({result.removed} removed)." if result.removed else "."),
            )
        return redirect("repositories:connect")

    def _handle_save(self, request):
        raw_ids = request.POST.getlist("repo_ids")
        selected_ids: list[int] = []
        for value in raw_ids:
            try:
                selected_ids.append(int(value))
            except (TypeError, ValueError):
                continue

        updated = update_repository_selection(
            request.user,
            selected_github_ids=selected_ids,
        )
        count = (
            Repository.objects.selected_for_user(request.user).count()
        )
        if count:
            label = "repository" if count == 1 else "repositories"
            changed = f" ({updated} changed.)" if updated else ""
            messages.success(
                request,
                f"Tracking {count} {label}.{changed}",
            )
        else:
            messages.info(
                request,
                "No repositories selected. Choose at least one to track, or refresh from GitHub.",
            )
        return redirect("repositories:connect")
