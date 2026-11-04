"""Persist RawFinding rows onto a Scan."""

from __future__ import annotations

import logging

from apps.findings.models import Finding
from apps.scans.models import Scan
from apps.scans.services.scanners.types import RawFinding

logger = logging.getLogger(__name__)

_VALID_SEVERITIES = {choice.value for choice in Finding.Severity}
_VALID_CATEGORIES = {choice.value for choice in Finding.Category}


def replace_findings_for_scan(scan: Scan, raw_findings: list[RawFinding]) -> int:
    """
    Idempotent write: delete existing findings for this scan, then insert anew.

    Returns the number of Finding rows created.
    """
    deleted, _ = Finding.objects.filter(scan=scan).delete()
    if deleted:
        logger.info(
            "Cleared previous findings scan_id=%s count=%s",
            scan.pk,
            deleted,
        )

    rows: list[Finding] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in raw_findings:
        severity = raw.severity if raw.severity in _VALID_SEVERITIES else Finding.Severity.INFO
        category = (
            raw.category if raw.category in _VALID_CATEGORIES else Finding.Category.OTHER
        )
        title = (raw.title or "Untitled finding").strip()[:512]
        file_path = (raw.file_path or "").strip()[:1024]
        key = (raw.rule_id or title, file_path, severity)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            Finding(
                scan=scan,
                title=title,
                severity=severity,
                category=category,
                summary=(raw.summary or "").strip() or "No summary provided.",
                recommendation=(raw.recommendation or "").strip()
                or "Review this finding and apply a fix appropriate for your stack.",
                file_path=file_path,
            )
        )

    if not rows:
        return 0
    Finding.objects.bulk_create(rows, batch_size=100)
    return len(rows)
