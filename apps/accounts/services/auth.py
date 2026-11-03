"""Create or update Django users from GitHub OAuth profiles."""

from __future__ import annotations

import re

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.accounts.models import GitHubAccount, GitHubInstallation
from apps.accounts.services.github import (
    GitHubInstallationInfo,
    GitHubUserProfile,
    OAuthTokenResponse,
)

User = get_user_model()

_USERNAME_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


def _unique_username(preferred: str) -> str:
    base = _USERNAME_SAFE.sub("-", preferred).strip(".-_")[:140] or "github-user"
    candidate = base
    suffix = 1
    while User.objects.filter(username=candidate).exists():
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


@transaction.atomic
def upsert_user_from_github(
    profile: GitHubUserProfile,
    token: OAuthTokenResponse,
) -> User:
    account = (
        GitHubAccount.objects.select_related("user")
        .filter(github_id=profile.github_id)
        .first()
    )
    if account:
        user = account.user
        if profile.email and user.email != profile.email:
            user.email = profile.email
        if profile.name and not user.first_name:
            user.first_name = profile.name[:150]
        user.save()
    else:
        user = User(
            username=_unique_username(profile.login),
            email=profile.email or "",
        )
        user.set_unusable_password()
        if profile.name:
            user.first_name = profile.name[:150]
        user.save()
        account = GitHubAccount(user=user, github_id=profile.github_id)

    account.login = profile.login
    account.avatar_url = profile.avatar_url
    account.access_token = token.access_token
    account.token_type = token.token_type
    account.scope = token.scope
    account.save()
    return user


@transaction.atomic
def sync_installations_for_user(
    user: User,
    installations: list[GitHubInstallationInfo],
) -> list[GitHubInstallation]:
    synced: list[GitHubInstallation] = []
    for info in installations:
        obj, _ = GitHubInstallation.objects.update_or_create(
            installation_id=info.installation_id,
            defaults={
                "account_login": info.account_login,
                "account_type": info.account_type,
                "account_id": info.account_id,
                "user": user,
            },
        )
        synced.append(obj)
    return synced


@transaction.atomic
def record_installation(
    *,
    installation_id: int,
    user: User | None,
    account_login: str = "",
    account_type: str = "User",
    account_id: int | None = None,
) -> GitHubInstallation:
    defaults = {
        "user": user,
        "account_login": account_login or f"installation-{installation_id}",
        "account_type": account_type,
        "account_id": account_id,
    }
    obj, created = GitHubInstallation.objects.get_or_create(
        installation_id=installation_id,
        defaults=defaults,
    )
    if not created:
        if user is not None:
            obj.user = user
        if account_login:
            obj.account_login = account_login
        if account_type:
            obj.account_type = account_type
        if account_id is not None:
            obj.account_id = account_id
        obj.save()
    return obj
