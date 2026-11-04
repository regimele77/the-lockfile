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
    verify_webhook_signature,
)

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class GithubWebhookView(View):
    """
    POST /accounts/github/webhook/

    Verifies X-Hub-Signature-256, then updates installations / repositories.
    """

    http_method_names = ["post"]

    def post(self, request):
        body = request.body or b""
        signature = request.headers.get("X-Hub-Signature-256") or request.META.get(
            "HTTP_X_HUB_SIGNATURE_256"
        )
        try:
            verify_webhook_signature(body=body, signature_header=signature)
        except WebhookVerificationError:
            logger.warning("GitHub webhook signature verification failed")
            return HttpResponseForbidden("invalid signature")

        event = request.headers.get("X-GitHub-Event") or request.META.get(
            "HTTP_X_GITHUB_EVENT", ""
        )
        if not event:
            return HttpResponseBadRequest("missing event")

        try:
            payload = json.loads(body.decode("utf-8") if body else "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return HttpResponseBadRequest("invalid json")
        if not isinstance(payload, dict):
            return HttpResponseBadRequest("invalid payload")

        # Never log the raw payload; delivery id is enough for correlation.
        delivery = request.headers.get("X-GitHub-Delivery") or request.META.get(
            "HTTP_X_GITHUB_DELIVERY", ""
        )
        try:
            status = handle_webhook_event(event, payload)
        except Exception:
            logger.exception(
                "GitHub webhook handler failed event=%s delivery=%s",
                event,
                delivery,
            )
            return HttpResponse("handler error", status=500)

        logger.info(
            "GitHub webhook processed event=%s delivery=%s status=%s",
            event,
            delivery,
            status,
        )
        return HttpResponse(status, content_type="text/plain")
