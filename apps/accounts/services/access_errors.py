"""Classify GitHub App / token failures and map them to recovery guidance.

Keep messages free of tokens and secrets. Prefer named URL reverses so templates
and flashes can offer a clear next step without blocking the rest of the app.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import Any
from urllib.parse import quote

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.services.github import GitHubAppError
from apps.accounts.services.installation_tokens import app_credentials_configured
from apps.accounts.services.secrets import TokenEncryptionError


class AccessFailureKind(str, Enum):
    MISSING_APP_CREDENTIALS = "missing_app_credentials"
    BAD_USER_TOKEN = "bad_user_token"
    TOKEN_DECRYPT = "token_decrypt"
    INSTALLATION_NOT_FOUND = "installation_not_found"
    GITHUB_UNAUTHORIZED = "github_unauthorized"
    GITHUB_FORBIDDEN = "github_forbidden"
    REPO_NOT_IN_INSTALLATION = "repo_not_in_installation"
    CLONE_PERMISSION_DENIED = "clone_permission_denied"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AccessFailureGuidance:
    kind: AccessFailureKind
    message: str
    primary_label: str = ""
    primary_url: str = ""
    secondary_label: str = ""
    secondary_url: str = ""

    @property
    def is_permission_related(self) -> bool:
        return self.kind in {
            AccessFailureKind.BAD_USER_TOKEN,
            AccessFailureKind.TOKEN_DECRYPT,
            AccessFailureKind.INSTALLATION_NOT_FOUND,
            AccessFailureKind.GITHUB_UNAUTHORIZED,
            AccessFailureKind.GITHUB_FORBIDDEN,
            AccessFailureKind.REPO_NOT_IN_INSTALLATION,
            AccessFailureKind.CLONE_PERMISSION_DENIED,
            AccessFailureKind.MISSING_APP_CREDENTIALS,
        }


def github_app_public_url() -> str:
    name = (settings.GITHUB_APP_NAME or "").strip()
    if not name:
        return ""
    return f"https://github.com/apps/{quote(name)}"


def github_installations_settings_url() -> str:
    """User-facing list of installed GitHub Apps (accept permission updates)."""
    return "https://github.com/settings/installations"


def github_installation_settings_url(installation_id: int | None = None) -> str:
    if installation_id:
        return f"https://github.com/settings/installations/{int(installation_id)}"
    return github_installations_settings_url()


def reconnect_url() -> str:
    return reverse("accounts:github_start")


def install_url() -> str:
    return reverse("accounts:github_install")


def connect_repos_url() -> str:
    return reverse("repositories:connect")


def profile_url() -> str:
    return reverse("accounts:profile")


def classify_exception(exc: BaseException) -> AccessFailureGuidance:
    """Map a known exception to user-facing recovery guidance."""
    if isinstance(exc, TokenEncryptionError):
        return AccessFailureGuidance(
            kind=AccessFailureKind.TOKEN_DECRYPT,
            message=(
                "Stored GitHub credentials could not be read. Re-connect GitHub "
                "so a fresh token can be saved with the current encryption key."
            ),
            primary_label="Re-connect GitHub",
            primary_url=reconnect_url(),
            secondary_label="Account settings",
            secondary_url=profile_url(),
        )

    return classify_message(str(exc or "").strip())


def classify_message(text: str) -> AccessFailureGuidance:
    """Classify free-form error text (scan errors, sync messages, API copy)."""
    cleaned = (text or "").strip()
    lowered = cleaned.lower()

    if _looks_like_missing_credentials(lowered):
        return AccessFailureGuidance(
            kind=AccessFailureKind.MISSING_APP_CREDENTIALS,
            message=(
                "GitHub App credentials are missing on this host. An operator "
                "must set GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY (or path) "
                "in .env, then restart Compose."
            ),
            primary_label="Account settings",
            primary_url=profile_url(),
        )

    if (
        "installation was not found" in lowered
        or "re-install the app" in lowered
        or "no github app installation" in lowered
        or "has no github app installation" in lowered
    ):
        return AccessFailureGuidance(
            kind=AccessFailureKind.INSTALLATION_NOT_FOUND,
            message=(
                "This GitHub App installation is missing or was removed. "
                "Install the App again and refresh repositories."
            ),
            primary_label="Install GitHub App",
            primary_url=install_url(),
            secondary_label="Refresh repositories",
            secondary_url=connect_repos_url(),
        )

    if "not in" in lowered and "installation" in lowered:
        return AccessFailureGuidance(
            kind=AccessFailureKind.REPO_NOT_IN_INSTALLATION,
            message=(
                "This repository is not in the GitHub App installation selection. "
                "Add it on GitHub, then refresh repositories."
            ),
            primary_label="Refresh repositories",
            primary_url=connect_repos_url(),
            secondary_label="Configure installation",
            secondary_url=github_installations_settings_url(),
        )

    if _looks_like_clone_denied(lowered):
        return AccessFailureGuidance(
            kind=AccessFailureKind.CLONE_PERMISSION_DENIED,
            message=(
                "Clone was denied. Confirm the App is installed on this repository, "
                "has Contents: Read, and that the repo is still in the installation "
                "selection. Then refresh repositories and try again."
            ),
            primary_label="Refresh repositories",
            primary_url=connect_repos_url(),
            secondary_label="Review App access",
            secondary_url=github_installations_settings_url(),
        )

    if (
        "rejected the app credentials or installation access" in lowered
        or "check app id, private key, and installation permissions" in lowered
    ):
        return AccessFailureGuidance(
            kind=AccessFailureKind.GITHUB_UNAUTHORIZED,
            message=(
                "GitHub rejected App credentials or installation access. Check "
                "App ID and private key, then re-install or accept updated "
                "permissions on the installation."
            ),
            primary_label="Accept App permissions",
            primary_url=github_installations_settings_url(),
            secondary_label="Install GitHub App",
            secondary_url=install_url(),
        )

    if (
        "missing permission" in lowered
        or "new permissions" in lowered
        or ("administration" in lowered and "read" in lowered)
        or ("branch protection" in lowered and "permission" in lowered)
        or "forbidden" in lowered
        or "http 403" in lowered
        or "status=403" in lowered
    ):
        app_url = github_app_public_url()
        return AccessFailureGuidance(
            kind=AccessFailureKind.GITHUB_FORBIDDEN,
            message=(
                "GitHub denied access (permission or scope). Update the App "
                "permissions if needed, then open the installation on GitHub and "
                "accept the new permissions. After that, refresh repositories."
            ),
            primary_label="Accept App permissions",
            primary_url=github_installations_settings_url(),
            secondary_label="App page" if app_url else "Refresh repositories",
            secondary_url=app_url or connect_repos_url(),
        )

    if (
        "http 401" in lowered
        or "unauthorized" in lowered
        or "bad credentials" in lowered
        or ("expired" in lowered and "token" in lowered)
        or ("oauth" in lowered and ("fail" in lowered or "denied" in lowered))
    ):
        return AccessFailureGuidance(
            kind=AccessFailureKind.BAD_USER_TOKEN,
            message=(
                "GitHub rejected the signed-in credentials. Re-connect GitHub "
                "to refresh your login token."
            ),
            primary_label="Re-connect GitHub",
            primary_url=reconnect_url(),
            secondary_label="Account settings",
            secondary_url=profile_url(),
        )

    return AccessFailureGuidance(
        kind=AccessFailureKind.UNKNOWN,
        message=cleaned or "GitHub access failed.",
        primary_label="Account settings",
        primary_url=profile_url(),
        secondary_label="Refresh repositories",
        secondary_url=connect_repos_url(),
    )


def _looks_like_missing_credentials(lowered: str) -> bool:
    markers = (
        "github_app_id",
        "private key",
        "app credentials",
        "credentials are incomplete",
        "credentials are not configured",
        "credentials are missing",
    )
    if not any(m in lowered for m in markers):
        return False
    return any(
        m in lowered
        for m in (
            "not configured",
            "incomplete",
            "required to",
            "set github_app_id",
            "missing",
        )
    )


def _looks_like_clone_denied(lowered: str) -> bool:
    if "clone failed" in lowered or "could not be cloned" in lowered:
        return True
    clone_markers = (
        "authentication failed",
        "could not read username",
        "invalid username or password",
        "remote: repository not found",
        "contents: read",
        "permission denied",
        "write access to repository not granted",
    )
    return any(m in lowered for m in clone_markers)


def user_facing_message(exc: BaseException) -> str:
    """Safe flash/inline message for an exception (no secrets)."""
    if isinstance(exc, (GitHubAppError, TokenEncryptionError)):
        return classify_exception(exc).message
    return classify_message(str(exc)).message


def connection_health(user) -> dict[str, Any]:
    """
    Lightweight GitHub connection summary for settings/profile.

    Avoids minting tokens. Surfaces recent permission-related scan failures.
    """
    from apps.accounts.models import GitHubAccount, GitHubInstallation
    from apps.scans.models import Scan

    account = GitHubAccount.objects.filter(user=user).first()
    installations = list(
        GitHubInstallation.objects.filter(user=user).order_by("account_login")
    )
    recent_failures = list(
        Scan.objects.filter(
            repository__owner=user,
            status=Scan.Status.FAILED,
            finished_at__gte=timezone.now() - timedelta(days=7),
        )
        .exclude(error_message="")
        .order_by("-finished_at")[:8]
    )
    permission_warning = ""
    for scan in recent_failures:
        guidance = classify_message(scan.error_message)
        if guidance.is_permission_related and guidance.kind != AccessFailureKind.UNKNOWN:
            permission_warning = guidance.message
            break

    return {
        "github_linked": account is not None,
        "github_login": account.login if account else "",
        "installation_count": len(installations),
        "installations": installations,
        "app_credentials_ready": app_credentials_configured(),
        "app_name": settings.GITHUB_APP_NAME or "",
        "app_public_url": github_app_public_url(),
        "permissions_url": github_installations_settings_url(),
        "permission_warning": permission_warning,
        "reconnect_url": reconnect_url(),
        "install_url": install_url(),
        "connect_repos_url": connect_repos_url(),
    }
