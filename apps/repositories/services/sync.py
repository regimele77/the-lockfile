"""Sync GitHub App installation repositories into the Repository model."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Iterable

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import GitHubInstallation
from apps.accounts.services.github import GitHubAppError, USER_AGENT
from apps.accounts.services.installation_tokens import (
    app_credentials_configured,
    get_installation_access_token,
)
from apps.repositories.models import Repository

logger = logging.getLogger(__name__)

_INSTALLATION_REPOS_URL = "https://api.github.com/installation/repositories"


@dataclass(frozen=True)
class RemoteRepository:
    github_id: int
    name: str
    full_name: str
    is_private: bool


@dataclass
class SyncResult:
    installations: int = 0
    upserted: int = 0
    removed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def sync_repositories_for_user(user) -> SyncResult:
    """Sync all installations owned by the user."""
    result = SyncResult()
    if not app_credentials_configured():
        result.errors.append(
            "GitHub App ID and private key are required to sync repositories."
        )
        return result

    installations = list(GitHubInstallation.objects.filter(user=user))
    if not installations:
        return result

    for installation in installations:
        try:
            partial = sync_repositories_for_installation(installation)
            result.installations += 1
            result.upserted += partial.upserted
            result.removed += partial.removed
        except GitHubAppError as exc:
            logger.warning(
                "Repo sync failed installation_id=%s",
                installation.installation_id,
            )
            result.errors.append(
                f"{installation.account_login}: {exc}"
            )
    return result


@transaction.atomic
def sync_repositories_for_installation(
    installation: GitHubInstallation,
) -> SyncResult:
    """
    List repositories for one installation and upsert local rows.

    Repos no longer returned by GitHub for this installation are deleted
    (selection state cannot survive membership loss).
    """
    result = SyncResult(installations=1)
    token = get_installation_access_token(installation.installation_id)
    remote_repos = list_installation_repositories(token.token)
    seen_github_ids: set[int] = set()

    for remote in remote_repos:
        seen_github_ids.add(remote.github_id)
        # update_or_create leaves is_selected / tracked_at untouched on update.
        Repository.objects.update_or_create(
            github_id=remote.github_id,
            defaults={
                "name": remote.name,
                "full_name": remote.full_name,
                "is_private": remote.is_private,
                "installation": installation,
                "owner": installation.user,
            },
        )
        result.upserted += 1

    stale_qs = Repository.objects.filter(installation=installation).exclude(
        github_id__in=seen_github_ids
    )
    removed_count, _ = stale_qs.delete()
    result.removed = removed_count
    return result


def update_repository_selection(
    user,
    *,
    selected_github_ids: Iterable[int],
) -> int:
    """
    Set is_selected for the user's repos based on the given GitHub ids.

    Only repositories belonging to the user's installations are touched.
    """
    selected_ids = {int(x) for x in selected_github_ids}
    now = timezone.now()
    qs = Repository.objects.for_user(user)
    updated = 0

    with transaction.atomic():
        for repo in qs.select_for_update():
            should_select = repo.github_id in selected_ids
            if repo.is_selected == should_select:
                continue
            repo.is_selected = should_select
            repo.tracked_at = now if should_select else None
            repo.save(update_fields=["is_selected", "tracked_at", "updated_at"])
            updated += 1
    return updated


def list_installation_repositories(access_token: str) -> list[RemoteRepository]:
    """Paginate GET /installation/repositories."""
    repos: list[RemoteRepository] = []
    url: str | None = f"{_INSTALLATION_REPOS_URL}?{urllib.parse.urlencode({'per_page': 100})}"

    while url:
        data, next_url = _authed_get_paginated(url, access_token)
        for item in data.get("repositories") or []:
            github_id = item.get("id")
            name = item.get("name")
            full_name = item.get("full_name")
            if not github_id or not name or not full_name:
                continue
            repos.append(
                RemoteRepository(
                    github_id=int(github_id),
                    name=str(name),
                    full_name=str(full_name),
                    is_private=bool(item.get("private")),
                )
            )
        url = next_url
    return repos


def upsert_remote_repositories(
    installation: GitHubInstallation,
    remotes: Iterable[RemoteRepository],
) -> int:
    """Upsert repos from webhook payloads without a full list sync."""
    count = 0
    for remote in remotes:
        Repository.objects.update_or_create(
            github_id=remote.github_id,
            defaults={
                "name": remote.name,
                "full_name": remote.full_name,
                "is_private": remote.is_private,
                "installation": installation,
                "owner": installation.user,
            },
        )
        count += 1
    return count


def delete_repositories_by_github_ids(github_ids: Iterable[int]) -> int:
    ids = [int(x) for x in github_ids]
    if not ids:
        return 0
    deleted, _ = Repository.objects.filter(github_id__in=ids).delete()
    return deleted


def remote_repo_from_payload(item: dict[str, Any]) -> RemoteRepository | None:
    github_id = item.get("id")
    name = item.get("name")
    full_name = item.get("full_name")
    if not github_id or not name or not full_name:
        return None
    return RemoteRepository(
        github_id=int(github_id),
        name=str(name),
        full_name=str(full_name),
        is_private=bool(item.get("private")),
    )


def _authed_get_paginated(
    url: str,
    access_token: str,
) -> tuple[dict[str, Any], str | None]:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {access_token}",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            next_url = _parse_next_link(response.headers.get("Link"))
    except urllib.error.HTTPError as exc:
        logger.warning(
            "GitHub installation repos HTTP error status=%s",
            exc.code,
        )
        if exc.code in (401, 403):
            raise GitHubAppError(
                "Missing permission to list repositories. "
                "Ensure the App has Metadata: Read."
            ) from exc
        raise GitHubAppError("GitHub API request failed.") from exc
    except urllib.error.URLError as exc:
        logger.warning("GitHub installation repos connection error")
        raise GitHubAppError("Could not reach GitHub.") from exc

    try:
        parsed = json.loads(body) if body else {}
    except json.JSONDecodeError as exc:
        raise GitHubAppError("GitHub returned an invalid response.") from exc
    if not isinstance(parsed, dict):
        raise GitHubAppError("GitHub returned an unexpected response shape.")
    return parsed, next_url


def _parse_next_link(link_header: str | None) -> str | None:
    if not link_header:
        return None
    # Format: <url>; rel="next", <url>; rel="last"
    for part in link_header.split(","):
        section = part.strip()
        if 'rel="next"' not in section:
            continue
        start = section.find("<")
        end = section.find(">")
        if start != -1 and end != -1 and end > start:
            return section[start + 1 : end]
    return None
