"""Create Scan rows and enqueue Celery work."""

from __future__ import annotations

import logging

from django.db import transaction

from apps.repositories.models import Repository
from apps.scans.models import Scan

logger = logging.getLogger(__name__)


class ScanStartError(Exception):
    """Raised when a scan cannot be started (auth, duplicate, config)."""


def repository_has_active_scan(repository: Repository) -> bool:
    return Scan.objects.filter(
        repository=repository,
        status__in=[Scan.Status.QUEUED, Scan.Status.RUNNING],
    ).exists()


@transaction.atomic
def enqueue_scan_for_repository(
    repository: Repository,
    *,
    trigger: str = Scan.Trigger.MANUAL,
    allow_duplicate: bool = False,
) -> Scan:
    """
    Create a queued Scan and dispatch the Celery task after commit.

    Raises ScanStartError if an active scan already exists (unless allow_duplicate).
    """
    if repository.pk is None:
        raise ScanStartError("Repository must be saved before scanning.")
    if not repository.is_selected:
        raise ScanStartError("Only tracked repositories can be scanned.")
    if not allow_duplicate and repository_has_active_scan(repository):
        raise ScanStartError(
            "A scan is already queued or running for this repository."
        )

    scan = Scan.objects.create(
        repository=repository,
        status=Scan.Status.QUEUED,
        trigger=trigger,
    )
    scan_id = scan.pk

    def _dispatch() -> None:
        # Import lazily so Django app loading does not require a running broker.
        from apps.scans.tasks import run_scan

        async_result = run_scan.delay(scan_id)
        Scan.objects.filter(pk=scan_id).update(
            celery_task_id=async_result.id or ""
        )
        logger.info(
            "Enqueued scan_id=%s repository_id=%s trigger=%s task_id=%s",
            scan_id,
            repository.pk,
            trigger,
            async_result.id,
        )

    transaction.on_commit(_dispatch)
    return scan
