"""Mint short-lived GitHub App installation access tokens.

Flow:
1. Sign a short-lived App JWT (RS256) with the App private key.
2. Exchange that JWT for an installation access token (~1 hour).

Tokens are minted on demand and must never be logged or rendered in templates.
Do not persist installation tokens as permanent credentials.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

import jwt
from django.conf import settings

from apps.accounts.github_keys import get_github_app_private_key
from apps.accounts.services.github import GitHubAppError, USER_AGENT

logger = logging.getLogger(__name__)

# GitHub allows App JWTs up to 10 minutes. Keep well under that.
_JWT_LIFETIME_SECONDS = 9 * 60
_INSTALLATION_TOKEN_URL = (
    "https://api.github.com/app/installations/{installation_id}/access_tokens"
)


@dataclass(frozen=True)
class InstallationAccessToken:
    token: str
    expires_at: str | None


def app_credentials_configured() -> bool:
    return bool(settings.GITHUB_APP_ID and get_github_app_private_key())


def create_app_jwt() -> str:
    """Build a short-lived GitHub App JWT signed with the App private key."""
    app_id = settings.GITHUB_APP_ID
    private_key = get_github_app_private_key()
    if not app_id or not private_key:
        raise GitHubAppError(
            "GitHub App credentials are incomplete. Set GITHUB_APP_ID and "
            "GITHUB_APP_PRIVATE_KEY (or GITHUB_APP_PRIVATE_KEY_PATH)."
        )

    now = int(time.time())
    payload = {
        "iat": now - 60,  # allow slight clock skew
        "exp": now + _JWT_LIFETIME_SECONDS,
        "iss": str(app_id),
    }
    try:
        return jwt.encode(payload, private_key, algorithm="RS256")
    except Exception as exc:
        logger.warning("Failed to sign GitHub App JWT")
        raise GitHubAppError("Could not sign GitHub App JWT. Check the private key.") from exc


def get_installation_access_token(installation_id: int) -> InstallationAccessToken:
    """
    Exchange an App JWT for an installation access token.

    The returned token typically expires in about one hour. Callers should
    mint on demand for each sync or API batch rather than caching long-term.
    """
    app_jwt = create_app_jwt()
    url = _INSTALLATION_TOKEN_URL.format(installation_id=int(installation_id))
    request = urllib.request.Request(
        url,
        data=b"",
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {app_jwt}",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    data = _json_request(request)
    token = data.get("token")
    if not token:
        raise GitHubAppError("GitHub did not return an installation access token.")
    return InstallationAccessToken(
        token=str(token),
        expires_at=str(data["expires_at"]) if data.get("expires_at") else None,
    )


def _json_request(request: urllib.request.Request) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        # Do not log response body; it may include sensitive details.
        logger.warning(
            "GitHub installation token HTTP error status=%s installation_path=%s",
            exc.code,
            request.full_url.split("?")[0],
        )
        if exc.code in (401, 403):
            raise GitHubAppError(
                "GitHub rejected the App credentials or installation access. "
                "Check App ID, private key, and installation permissions."
            ) from exc
        if exc.code == 404:
            raise GitHubAppError(
                "GitHub App installation was not found. Re-install the App."
            ) from exc
        raise GitHubAppError("GitHub API request failed.") from exc
    except urllib.error.URLError as exc:
        logger.warning("GitHub installation token connection error")
        raise GitHubAppError("Could not reach GitHub.") from exc

    try:
        parsed = json.loads(body) if body else {}
    except json.JSONDecodeError as exc:
        raise GitHubAppError("GitHub returned an invalid response.") from exc
    if not isinstance(parsed, dict):
        raise GitHubAppError("GitHub returned an unexpected response shape.")
    return parsed
