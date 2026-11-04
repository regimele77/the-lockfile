"""Persist RawFinding rows onto a Scan."""

from __future__ import annotations

import logging
from pathlib import Path

from apps.findings.models import Finding, path_never_on_github
from apps.scans.models import Scan
from apps.scans.services.scanners.common import path_in_git_head
from apps.scans.services.scanners.types import RawFinding

logger = logging.getLogger(__name__)

_VALID_SEVERITIES = {choice.value for choice in Finding.Severity}
_VALID_CATEGORIES = {choice.value for choice in Finding.Category}
_TERMINAL_STATUSES = {Finding.Status.RESOLVED, Finding.Status.IGNORED}


def _identity_key(*, rule_id: str, file_path: str, title: str) -> tuple[str, str]:
    """Stable key used to carry triage status across scan runs."""
    identity = (rule_id or title or "").strip()
    return (identity, (file_path or "").strip())


def _prior_status_map(scan: Scan) -> dict[tuple[str, str], str]:
    """
    Map (rule_id|title, file_path) -> ignored/resolved status for this repo.

    Uses the newest matching finding per identity (including this scan before a
    re-run). Only terminal statuses are returned so a reopened item stays open.
    """
    newest: dict[tuple[str, str], str] = {}

    prior = (
        Finding.objects.filter(scan__repository_id=scan.repository_id)
        .order_by("-created_at")
        .only("rule_id", "file_path", "title", "status")
    )
    for finding in prior:
        key = _identity_key(
            rule_id=finding.rule_id,
            file_path=finding.file_path,
            title=finding.title,
        )
        if not key[0] or key in newest:
            continue
        newest[key] = finding.status

    return {key: status for key, status in newest.items() if status in _TERMINAL_STATUSES}


def _supersede_prior_open_findings(scan: Scan) -> int:
    """
    Mark open findings from older scans on this repo as resolved.

    The newest completed scan is the source of truth; keeping older open rows
    leaves stale paths and duplicate issues in the findings list.
    """
    updated = (
        Finding.objects.filter(
            scan__repository_id=scan.repository_id,
            status=Finding.Status.OPEN,
        )
        .exclude(scan_id=scan.pk)
        .update(status=Finding.Status.RESOLVED)
    )
    if updated:
        logger.info(
            "Superseded prior open findings repository_id=%s count=%s newer_scan_id=%s",
            scan.repository_id,
            updated,
            scan.pk,
        )
    return updated


def _resolve_github_linkable(
    *,
    file_path: str,
    explicit: bool | None,
    workspace: Path | None,
) -> bool:
    """Only link paths that exist in the scanned commit on GitHub."""
    path = (file_path or "").strip().lstrip("/")
    if not path or path_never_on_github(path):
        return False
    if explicit is False:
        return False
    if explicit is True and workspace is None:
        return True
    if workspace is None:
        # Without a workspace we cannot verify; prefer no broken link.
        return False
    return path_in_git_head(workspace, path)


def replace_findings_for_scan(
    scan: Scan,
    raw_findings: list[RawFinding],
    *,
    workspace: Path | None = None,
) -> int:
    """
    Idempotent write: delete existing findings for this scan, then insert anew.

    Ignored/resolved triage is preserved when the same rule_id+file_path (or
    title+file_path fallback) was already triaged on this repository.

    After insert, open findings from older scans on the same repository are
    marked resolved so the findings list tracks the latest scan.

    Returns the number of Finding rows created.
    """
    prior_statuses = _prior_status_map(scan)

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
        # Never pass None into NOT NULL columns (bulk_create does not always
        # apply model defaults the way save() does).
        rule_id = ((raw.rule_id or "").strip() or "")[:128]
        key = (rule_id or title, file_path, severity)
        if key in seen:
            continue
        seen.add(key)

        identity = _identity_key(rule_id=rule_id, file_path=file_path, title=title)
        status = Finding.Status.OPEN
        prior = prior_statuses.get(identity)
        if prior in _TERMINAL_STATUSES:
            status = prior

        line_number = raw.line_number if raw.line_number and raw.line_number > 0 else None
        github_linkable = _resolve_github_linkable(
            file_path=file_path,
            explicit=raw.github_linkable,
            workspace=workspace,
        )

        rows.append(
            Finding(
                scan=scan,
                title=title,
                severity=severity,
                category=category,
                status=status or Finding.Status.OPEN,
                summary=(raw.summary or "").strip() or "No summary provided.",
                recommendation=(raw.recommendation or "").strip()
                or "Review this finding and apply a fix appropriate for your stack.",
                file_path=file_path,
                rule_id=rule_id,
                line_number=line_number,
                github_linkable=github_linkable,
            )
        )

    if rows:
        Finding.objects.bulk_create(rows, batch_size=100)

    _supersede_prior_open_findings(scan)
    return len(rows)
