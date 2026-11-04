"""Stage-aware empty-state copy for the connect -> select -> scan -> review loop."""

from __future__ import annotations

from dataclasses import dataclass

from django.urls import reverse

from apps.accounts.models import GitHubInstallation
from apps.findings.models import Finding
from apps.repositories.models import Repository
from apps.scans.models import Scan


@dataclass(frozen=True)
class Guidance:
    stage: str
    title: str
    description: str
    action_url: str
    action_label: str


def onboarding_guidance(user) -> Guidance:
    """
    Return the next step for a signed-in user based on installations, repos,
    scans, and open findings.
    """
    has_installation = GitHubInstallation.objects.filter(user=user).exists()
    if not has_installation:
        return Guidance(
            stage="no_installation",
            title="Connect GitHub to get started",
            description=(
                "Install the GitHub App on your user or organization account, "
                "then pick repositories to track on this host."
            ),
            action_url=reverse("accounts:github_install"),
            action_label="Install GitHub App",
        )

    repos = Repository.objects.selected_for_user(user)
    if not repos.exists():
        return Guidance(
            stage="no_repos",
            title="Select repositories to track",
            description=(
                "Your GitHub App is installed. Choose which repos The Lockfile "
                "may scan, then save the selection."
            ),
            action_url=reverse("repositories:connect"),
            action_label="Pick repositories",
        )

    if not Scan.objects.filter(repository__in=repos).exists():
        first_repo = repos.order_by("full_name").first()
        action_url = (
            reverse("repositories:detail", args=[first_repo.pk])
            if first_repo
            else reverse("repositories:list")
        )
        return Guidance(
            stage="no_scans",
            title="Run your first scan",
            description=(
                "Tracked repositories are ready. Open a repo and click Run scan "
                "to clone the default branch and produce findings."
            ),
            action_url=action_url,
            action_label="Open a repository",
        )

    open_findings = Finding.objects.filter(
        scan__repository__in=repos,
        status=Finding.Status.OPEN,
    )
    if not open_findings.exists():
        return Guidance(
            stage="no_open_findings",
            title="No open findings",
            description=(
                "Scans have finished and nothing is waiting for triage. "
                "Review past scans, or run another scan after you change code."
            ),
            action_url=reverse("scans:list"),
            action_label="View scans",
        )

    return Guidance(
        stage="has_open_findings",
        title="Review open findings",
        description=(
            "Open findings from your tracked repos are ready for triage. "
            "Mark them resolved or ignored as you work through the list."
        ),
        action_url=reverse("findings:list"),
        action_label="Review findings",
    )
