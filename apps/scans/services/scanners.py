"""Scanner extension point run after a successful clone.

Finding creation and real vulnerability / secret / config scanners belong
to the next milestone. Keep this module as the single hook Celery calls.
"""

from __future__ import annotations

import logging
from pathlib import Path

from apps.scans.models import Scan

logger = logging.getLogger(__name__)


def run_scanners(*, scan: Scan, workspace: Path) -> int:
    """
    Run security scanners against the cloned workspace.

    Returns the number of findings created. Currently a no-op placeholder so
    a successful clone completes the scan with zero findings.
    """
    logger.info(
        "Scanner placeholder scan_id=%s workspace=%s commit=%s",
        scan.pk,
        workspace.name,
        scan.commit_sha or "-",
    )
    # Next milestone: invoke secret, dependency, config, and workflow scanners
    # here and persist Finding rows linked to this scan.
    return 0
