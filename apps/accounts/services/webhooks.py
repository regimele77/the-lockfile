"""Handle GitHub App webhook events for installations and repository membership."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

from django.conf import settings

from apps.accounts.models import GitHubInstallation, WebhookDeliveryLog
from apps.accounts.services.auth import record_installation
from apps.repositories.services.sync import (
    delete_repositories_by_github_ids,
    remote_repo_from_payload,
    upsert_remote_repositories,
)

logger = logging.getLogger(__name__)


class WebhookVerificationError(Exception):
    """Raised when the webhook signature is missing or invalid."""


def verify_webhook_signature(*, body: bytes, signature_header: str | None) -> None:
    """
    Validate X-Hub-Signature-256 using GITHUB_APP_WEBHOOK_SECRET.

    GitHub sends: sha256=<hex hmac of raw body>

    Behavior when the secret is empty:
    - DEBUG=True: accept the delivery and log a warning (local tunnel convenience).
    - DEBUG=False: fail closed (reject). Production-like settings always require
      a configured secret and a valid signature.
    """
    secret = (settings.GITHUB_APP_WEBHOOK_SECRET or "").strip()
    if not secret:
        if settings.DEBUG:
            logger.warning(
                "GITHUB_APP_WEBHOOK_SECRET is empty; accepting unsigned webhook "
                "(DEBUG only). Set the secret before any non-local deploy."
            )
            return
        raise WebhookVerificationError("Webhook secret is not configured.")

    if not signature_header or not signature_header.startswith("sha256="):
        raise WebhookVerificationError("Missing or malformed signature header.")

    expected = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    received = signature_header.removeprefix("sha256=")
    if not hmac.compare_digest(expected, received):
        raise WebhookVerificationError("Invalid webhook signature.")


def record_webhook_delivery(
    *,
    delivery_id: str,
    event: str,
    action: str = "",
    ok: bool = True,
    status: str = "",
    error: str = "",
) -> None:
    """Persist a lean delivery row without payload bodies."""
    try:
        WebhookDeliveryLog.objects.create(
            delivery_id=(delivery_id or "")[:64],
            event=(event or "")[:64],
            action=(action or "")[:64],
            ok=ok,
            status=(status or "")[:64],
            error=(error or "")[:255],
        )
    except Exception:
        # Delivery logging must never break webhook handling.
        logger.exception(
            "Failed to persist webhook delivery log delivery=%s event=%s",
            delivery_id,
            event,
        )


def handle_webhook_event(event: str, payload: dict[str, Any]) -> str:
    """
    Dispatch a verified webhook event.

    Returns a short status string for the HTTP response body.
    Does not log raw payloads (may include sensitive account details).
    """
    action = str(payload.get("action") or "")

    if event == "ping":
        return "pong"
    if event == "installation":
        return _handle_installation(action, payload)
    if event == "installation_repositories":
        return _handle_installation_repositories(action, payload)

    logger.info("Ignored GitHub webhook event=%s action=%s", event, action)
    return "ignored"


def _handle_installation(action: str, payload: dict[str, Any]) -> str:
    installation_data = payload.get("installation") or {}
    installation_id = installation_data.get("id")
    if not installation_id:
        return "missing-installation"

    installation_id = int(installation_id)
    account = installation_data.get("account") or {}
    account_login = str(account.get("login") or f"installation-{installation_id}")
    account_type = str(account.get("type") or "User")
    account_id = account.get("id")
    account_id_int = int(account_id) if account_id is not None else None

    if action in ("deleted", "suspend"):
        deleted, _ = GitHubInstallation.objects.filter(
            installation_id=installation_id
        ).delete()
        logger.info(
            "Webhook installation action=%s installation_id=%s deleted=%s",
            action,
            installation_id,
            deleted,
        )
        return f"installation-{action}"

    if action in ("created", "unsuspend", "new_permissions_accepted"):
        # Keep existing user link when present; do not invent ownership.
        existing = GitHubInstallation.objects.filter(
            installation_id=installation_id
        ).first()
        record_installation(
            installation_id=installation_id,
            user=existing.user if existing else None,
            account_login=account_login,
            account_type=account_type,
            account_id=account_id_int,
        )
        # On create, also ingest repositories_added if present.
        if action == "created":
            installation = GitHubInstallation.objects.filter(
                installation_id=installation_id
            ).first()
            if installation:
                remotes = []
                for item in payload.get("repositories") or []:
                    remote = remote_repo_from_payload(item)
                    if remote:
                        remotes.append(remote)
                if remotes:
                    upsert_remote_repositories(installation, remotes)
        logger.info(
            "Webhook installation action=%s installation_id=%s",
            action,
            installation_id,
        )
        return f"installation-{action}"

    logger.info("Ignored installation action=%s installation_id=%s", action, installation_id)
    return "ignored"


def _handle_installation_repositories(action: str, payload: dict[str, Any]) -> str:
    installation_data = payload.get("installation") or {}
    installation_id = installation_data.get("id")
    if not installation_id:
        return "missing-installation"

    installation = GitHubInstallation.objects.filter(
        installation_id=int(installation_id)
    ).first()
    if installation is None:
        # Record a stub so a later OAuth/setup can claim it.
        account = installation_data.get("account") or {}
        installation = record_installation(
            installation_id=int(installation_id),
            user=None,
            account_login=str(account.get("login") or f"installation-{installation_id}"),
            account_type=str(account.get("type") or "User"),
            account_id=int(account["id"]) if account.get("id") is not None else None,
        )

    if action == "added":
        remotes = []
        for item in payload.get("repositories_added") or []:
            remote = remote_repo_from_payload(item)
            if remote:
                remotes.append(remote)
        count = upsert_remote_repositories(installation, remotes)
        logger.info(
            "Webhook repos added installation_id=%s count=%s",
            installation.installation_id,
            count,
        )
        return "repositories-added"

    if action == "removed":
        github_ids = []
        for item in payload.get("repositories_removed") or []:
            rid = item.get("id")
            if rid is not None:
                github_ids.append(int(rid))
        count = delete_repositories_by_github_ids(github_ids)
        logger.info(
            "Webhook repos removed installation_id=%s count=%s",
            installation.installation_id,
            count,
        )
        return "repositories-removed"

    logger.info(
        "Ignored installation_repositories action=%s installation_id=%s",
        action,
        installation.installation_id,
    )
    return "ignored"
