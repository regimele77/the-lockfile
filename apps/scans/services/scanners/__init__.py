"""Security scanners run after a successful clone.

Celery calls :func:`run_scanners` as the single extension hook. Individual
checkers live in sibling modules and return :class:`RawFinding` lists.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from apps.scans.models import Scan
from apps.scans.services.scanners.configs import scan_configs
from apps.scans.services.scanners.dependencies import scan_dependencies
from apps.scans.services.scanners.persist import replace_findings_for_scan
from apps.scans.services.scanners.practices import scan_practices
from apps.scans.services.scanners.secrets import scan_secrets
from apps.scans.services.scanners.types import RawFinding
from apps.scans.services.scanners.workflows import scan_workflows

logger = logging.getLogger(__name__)


def run_scanners(*, scan: Scan, workspace: Path) -> int:
    """
    Run all enabled scanners against the cloned workspace and persist findings.

    Returns the number of Finding rows created. One scanner failing is logged
    and skipped so other scanners can still contribute. Catastrophic workspace
    problems raise to fail the scan.
    """
    if not workspace.is_dir():
        raise FileNotFoundError(f"Scan workspace is missing: {workspace}")

    logger.info(
        "Running scanners scan_id=%s workspace=%s commit=%s",
        scan.pk,
        workspace.name,
        scan.commit_sha or "-",
    )

    collected: list[RawFinding] = []
    scanner_errors: list[str] = []

    file_scanners: list[tuple[str, Callable[..., list[RawFinding]]]] = [
        ("secrets", lambda: scan_secrets(workspace=workspace)),
        ("dependencies", lambda: scan_dependencies(workspace=workspace)),
        ("configs", lambda: scan_configs(workspace=workspace)),
        ("workflows", lambda: scan_workflows(workspace=workspace)),
    ]
    for name, runner in file_scanners:
        try:
            results = runner()
            collected.extend(results)
            logger.info(
                "Scanner %s scan_id=%s findings=%s",
                name,
                scan.pk,
                len(results),
            )
        except Exception:
            logger.exception("Scanner %s failed scan_id=%s", name, scan.pk)
            scanner_errors.append(name)

    try:
        practice_results = scan_practices(scan=scan)
        collected.extend(practice_results)
        logger.info(
            "Scanner practices scan_id=%s findings=%s",
            scan.pk,
            len(practice_results),
        )
    except Exception:
        logger.exception("Scanner practices failed scan_id=%s", scan.pk)
        scanner_errors.append("practices")

    if scanner_errors:
        collected.append(
            RawFinding(
                title="Some scanners did not finish cleanly",
                severity="info",
                category="other",
                summary=(
                    "One or more scanners raised an unexpected error and were skipped: "
                    + ", ".join(scanner_errors)
                    + ". Other scanners still ran."
                ),
                recommendation=(
                    "Check worker logs for the scanner traceback. Re-run the scan after "
                    "fixing the underlying issue."
                ),
                rule_id="scanner.partial_failure",
            )
        )

    count = replace_findings_for_scan(scan, collected, workspace=workspace)
    logger.info(
        "Scanners complete scan_id=%s findings_created=%s",
        scan.pk,
        count,
    )
    return count
