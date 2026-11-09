"""Inbound GitHub App webhook endpoint."""

from __future__ import annotations

import json
import logging

from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.accounts.services.webhooks import (
    WebhookVerificationError,
    handle_webhook_event,
    record_webhook_delivery,
    verify_webhook_signature,
)

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class GithubWebhookView(View):
    """
    POST /accounts/github/webhook/

    Verifies X-Hub-Signature-256, then updates installations / repositories.
    CSRF is exempt; authenticity is signature-based.
    """

    http_method_names = ["post"]

    def post(self, request):
        body = request.body or b""
        delivery = request.headers.get("X-GitHub-Delivery") or request.META.get(
            "HTTP_X_GITHUB_DELIVERY", ""
        )
        event = request.headers.get("X-GitHub-Event") or request.META.get(
            "HTTP_X_GITHUB_EVENT", ""
        )
        signature = request.headers.get("X-Hub-Signature-256") or request.META.get(
            "HTTP_X_HUB_SIGNATURE_256"
        )

        try:
            verify_webhook_signature(body=body, signature_header=signature)
        except WebhookVerificationError:
            logger.warning(
                "GitHub webhook signature verification failed delivery=%s event=%s",
                delivery,
                event,
            )
            record_webhook_delivery(
                delivery_id=delivery,
                event=event or "unknown",
                ok=False,
                status="invalid-signature",
                error="invalid signature",
            )
            return HttpResponseForbidden("invalid signature")

        if not event:
            record_webhook_delivery(
                delivery_id=delivery,
                event="",
                ok=False,
                status="missing-event",
                error="missing event",
            )
            return HttpResponseBadRequest("missing event")

        try:
            payload = json.loads(body.decode("utf-8") if body else "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            record_webhook_delivery(
                delivery_id=delivery,
                event=event,
                ok=False,
                status="invalid-json",
                error="invalid json",
            )
            return HttpResponseBadRequest("invalid json")
        if not isinstance(payload, dict):
            record_webhook_delivery(
                delivery_id=delivery,
                event=event,
                ok=False,
                status="invalid-payload",
                error="invalid payload",
            )
            return HttpResponseBadRequest("invalid payload")

        # Never log the raw payload; delivery id is the main correlation key.
        action = str(payload.get("action") or "")
        try:
            status = handle_webhook_event(event, payload)
        except Exception:
            logger.exception(
                "GitHub webhook handler failed delivery=%s event=%s action=%s",
                delivery,
                event,
                action,
            )
            record_webhook_delivery(
                delivery_id=delivery,
                event=event,
                action=action,
                ok=False,
                status="handler-error",
                error="handler error",
            )
            return HttpResponse("handler error", status=500)

        # Ignored / handled events return 200 with a short status string so
        # GitHub does not retry storms on intentionally unsupported events.
        logger.info(
            "GitHub webhook processed delivery=%s event=%s action=%s status=%s",
            delivery,
            event,
            action,
            status,
        )
        record_webhook_delivery(
            delivery_id=delivery,
            event=event,
            action=action,
            ok=True,
            status=status,
        )
        return HttpResponse(status, content_type="text/plain")
