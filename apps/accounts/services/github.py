"""GitHub App user-to-server OAuth helpers.

Tokens and secrets must never be logged. Callers should treat access tokens
as sensitive and keep them off templates and log lines.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from django.conf import settings

logger = logging.getLogger(__name__)

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_USER_URL = "https://api.github.com/user"
GITHUB_API_INSTALLATIONS_URL = "https://api.github.com/user/installations"
USER_AGENT = "the-lockfile"


class GitHubAppError(Exception):
    """Raised when GitHub OAuth or API calls fail in an expected way."""


@dataclass(frozen=True)
class OAuthTokenResponse:
    access_token: str
    token_type: str
    scope: str


@dataclass(frozen=True)
class GitHubUserProfile:
    github_id: int
    login: str
    email: str
    name: str
    avatar_url: str


@dataclass(frozen=True)
class GitHubInstallationInfo:
    installation_id: int
    account_login: str
    account_type: str
    account_id: int | None


class GitHubOAuthClient:
    def __init__(self) -> None:
        self.client_id = settings.GITHUB_APP_CLIENT_ID
        self.client_secret = settings.GITHUB_APP_CLIENT_SECRET
        self.callback_url = settings.GITHUB_OAUTH_CALLBACK_URL
        self.app_name = settings.GITHUB_APP_NAME

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.callback_url)

    def authorize_url(self, state: str) -> str:
        if not self.is_configured():
            raise GitHubAppError("GitHub App OAuth is not configured.")
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.callback_url,
            "state": state,
            # Request identity fields needed for Django user creation.
            "scope": "read:user user:email",
        }
        return f"{GITHUB_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    def install_url(self, state: str | None = None) -> str:
        if not self.app_name:
            raise GitHubAppError("GITHUB_APP_NAME is not configured.")
        base = f"https://github.com/apps/{urllib.parse.quote(self.app_name)}/installations/new"
        if state:
            return f"{base}?{urllib.parse.urlencode({'state': state})}"
        return base

    def callback_host_allowed(self, request_host: str) -> bool:
        """Restrict OAuth completion to the configured callback host."""
        configured = urlparse(self.callback_url)
        if not configured.hostname:
            return False
        incoming = request_host.split(":")[0].lower()
        expected = configured.hostname.lower()
        return incoming == expected

    def exchange_code(self, code: str) -> OAuthTokenResponse:
        if not self.is_configured():
            raise GitHubAppError("GitHub App OAuth is not configured.")
        payload = urllib.parse.urlencode(
            {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": self.callback_url,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            GITHUB_TOKEN_URL,
            data=payload,
            method="POST",
            headers={
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        data = self._json_request(request)
        token = data.get("access_token")
        if not token:
            # Do not include GitHub's error_description in logs if it might leak secrets.
            raise GitHubAppError("GitHub did not return an access token.")
        return OAuthTokenResponse(
            access_token=token,
            token_type=str(data.get("token_type") or "bearer"),
            scope=str(data.get("scope") or ""),
        )

    def fetch_user(self, access_token: str) -> GitHubUserProfile:
        data = self._authed_get(GITHUB_API_USER_URL, access_token)
        github_id = data.get("id")
        login = data.get("login")
        if not github_id or not login:
            raise GitHubAppError("GitHub user profile was incomplete.")
        return GitHubUserProfile(
            github_id=int(github_id),
            login=str(login),
            email=str(data.get("email") or ""),
            name=str(data.get("name") or ""),
            avatar_url=str(data.get("avatar_url") or ""),
        )

    def list_installations(self, access_token: str) -> list[GitHubInstallationInfo]:
        data = self._authed_get(GITHUB_API_INSTALLATIONS_URL, access_token)
        installations: list[GitHubInstallationInfo] = []
        for item in data.get("installations") or []:
            account = item.get("account") or {}
            installation_id = item.get("id")
            account_login = account.get("login")
            if not installation_id or not account_login:
                continue
            account_id = account.get("id")
            installations.append(
                GitHubInstallationInfo(
                    installation_id=int(installation_id),
                    account_login=str(account_login),
                    account_type=str(account.get("type") or "User"),
                    account_id=int(account_id) if account_id is not None else None,
                )
            )
        return installations

    def _authed_get(self, url: str, access_token: str) -> dict[str, Any]:
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
        return self._json_request(request)

    def _json_request(self, request: urllib.request.Request) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            # Intentionally omit response body — may contain sensitive details.
            logger.warning("GitHub API HTTP error status=%s path=%s", exc.code, request.full_url)
            raise GitHubAppError("GitHub API request failed.") from exc
        except urllib.error.URLError as exc:
            logger.warning("GitHub API connection error path=%s", request.full_url)
            raise GitHubAppError("Could not reach GitHub.") from exc

        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            raise GitHubAppError("GitHub returned an invalid response.") from exc
        if not isinstance(parsed, dict):
            raise GitHubAppError("GitHub returned an unexpected response shape.")
        return parsed
