"""Load the GitHub App private key for future installation-token minting."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings


def get_github_app_private_key() -> str:
    """
    Return PEM private key material from env contents or a path.

    Installation access tokens expire in about one hour. Mint them on demand
    with an App JWT; do not persist them as long-lived secrets.
    """
    if settings.GITHUB_APP_PRIVATE_KEY:
        return settings.GITHUB_APP_PRIVATE_KEY
    path = settings.GITHUB_APP_PRIVATE_KEY_PATH
    if path:
        return Path(path).read_text(encoding="utf-8")
    return ""
