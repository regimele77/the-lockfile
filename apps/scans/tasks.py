"""Celery tasks for the scan pipeline."""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.db import IntegrityError
from django.db.models import Max, Q
from django.utils import timezone

from apps.accounts.services.access_errors import classify_exception, classify_message
from apps.accounts.services.github import GitHubAppError
from apps.accounts.services.installation_tokens import (
    app_credentials_configured,
    get_installation_access_token,
)
from apps.repositories.models import Repository
from apps.scans.models import Scan
from apps.scans.services.clone import (
    CloneError,
    cleanup_workspace,
    clone_repository,
    prepare_scan_workspace,
)
from apps.scans.services.enqueue import (
    ScanStartError,
    enqueue_scan_for_repository,
    repository_has_active_scan,
)
from apps.scans.services.sanitize import sanitize_error_message
from apps.scans.services.scanners import run_scanners

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="apps.scans.tasks.run_scan", max_retries=0)
def run_scan(self, scan_id: int) -> str:
    """
    Execute one scan: mark running, clone, run scanner hook, mark completed/failed.

    Workspace cleanup always runs in finally. Tokens are never logged.
    """
    try:
        scan = Scan.objects.select_related(
            "repository",
            "repository__installation",
        ).get(pk=scan_id)
    except Scan.DoesNotExist:
        logger.warning("run_scan missing scan_id=%s", scan_id)
        return "missing"

    if scan.status not in {Scan.Status.QUEUED, Scan.Status.RUNNING}:
        logger.info(
            "run_scan skip scan_id=%s status=%s",
            scan_id,
            scan.status,
        )
        return scan.status

    workspace: Path | None = None
    try:
        scan.status = Scan.Status.RUNNING
        scan.started_at = timezone.now()
        scan.error_message = ""
        scan.save(update_fields=["status", "started_at", "error_message"])

        if not app_credentials_configured():
            raise CloneError(
                "GitHub App credentials are not configured on the worker. "
                "Set GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY."
            )

        installation = scan.repository.installation
        if installation is None:
            raise CloneError(
                "Repository has no GitHub App installation. "
                "Re-install the App and refresh repositories."
            )

        token = get_installation_access_token(installation.installation_id)
        workspace = prepare_scan_workspace(scan.pk)
        result = clone_repository(
            full_name=scan.repository.full_name,
            access_token=token.token,
            destination=workspace,
        )
        scan.commit_sha = result.commit_sha
        scan.default_branch = result.default_branch
        scan.save(update_fields=["commit_sha", "default_branch"])

        run_scanners(scan=scan, workspace=result.workspace)

        scan.status = Scan.Status.COMPLETED
        scan.finished_at = timezone.now()
        scan.error_message = ""
        scan.save(update_fields=["status", "finished_at", "error_message"])
        logger.info(
            "Scan completed scan_id=%s repository=%s commit=%s",
            scan.pk,
            scan.repository.full_name,
            scan.commit_sha,
        )
        return "completed"
    except (CloneError, GitHubAppError) as exc:
        guidance = classify_exception(exc)
        _fail_scan(scan, guidance.message if guidance.kind.value != "unknown" else str(exc))
        return "failed"
    except IntegrityError:
        logger.exception("Scan findings could not be saved scan_id=%s", scan_id)
        _fail_scan(
            scan,
            "Scan failed while saving findings. Re-run the scan; if it keeps "
            "failing, check worker logs for a database constraint error.",
        )
        return "failed"
    except Exception:
        logger.exception("Unexpected scan failure scan_id=%s", scan_id)
        _fail_scan(scan, "Scan failed due to an unexpected error.")
        return "failed"
    finally:
        cleanup_workspace(workspace)


def _fail_scan(scan: Scan, message: str) -> None:
    cleaned = sanitize_error_message(message)
    guidance = classify_message(cleaned)
    # Prefer classified recovery copy when the raw text is cryptic clone stderr.
    if guidance.kind.value != "unknown":
        cleaned = sanitize_error_message(guidance.message)
    scan.status = Scan.Status.FAILED
    scan.finished_at = timezone.now()
    scan.error_message = cleaned
    scan.save(update_fields=["status", "finished_at", "error_message"])
    logger.warning(
        "Scan failed scan_id=%s repository=%s",
        scan.pk,
        scan.repository_id,
    )


@shared_task(name="apps.scans.tasks.enqueue_due_scans")
def enqueue_due_scans() -> int:
    """
    Enqueue scheduled scans for tracked repos that are due.

    A repo is due when it has no queued/running scan and either:
    - has never been scanned, or
    - its latest finished scan is older than SCAN_RESCHEDULE_HOURS.
    """
    hours = max(1, int(settings.SCAN_RESCHEDULE_HOURS))
    cutoff = timezone.now() - timedelta(hours=hours)
    enqueued = 0

    repos = (
        Repository.objects.filter(is_selected=True)
        .select_related("installation")
        .annotate(
            last_finished=Max(
                "scans__finished_at",
                filter=Q(
                    scans__status__in=[
                        Scan.Status.COMPLETED,
                        Scan.Status.FAILED,
                    ]
                ),
            )
        )
        .order_by("id")
    )

    for repo in repos.iterator():
        if repository_has_active_scan(repo):
            continue
        last_finished = repo.last_finished
        if last_finished is not None and last_finished > cutoff:
            continue
        try:
            enqueue_scan_for_repository(
                repo,
                trigger=Scan.Trigger.SCHEDULED,
            )
            enqueued += 1
        except ScanStartError:
            continue
        except Exception:
            logger.exception(
                "Scheduled enqueue failed repository_id=%s",
                repo.pk,
            )

    logger.info("Scheduled scan enqueue complete count=%s", enqueued)
    return enqueued
