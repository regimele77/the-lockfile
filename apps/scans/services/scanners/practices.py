"""Missing GitHub repository practices via the installation API."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from django.conf import settings

from apps.accounts.services.github import GitHubAppError, USER_AGENT
from apps.accounts.services.installation_tokens import get_installation_access_token
from apps.findings.models import Finding
from apps.scans.models import Scan
from apps.scans.services.scanners.common import new_budget, scanner_enabled
from apps.scans.services.scanners.types import RawFinding

logger = logging.getLogger(__name__)


def scan_practices(*, scan: Scan) -> list[RawFinding]:
    if not scanner_enabled("SCANNER_ENABLE_PRACTICES", True):
        return []

    budget = new_budget()
    repo = scan.repository
    installation = repo.installation
    if installation is None:
        return []

    owner_repo = repo.full_name
    if "/" not in owner_repo:
        return []
    owner, name = owner_repo.split("/", 1)
    branch = (scan.default_branch or "").strip() or "main"

    try:
        token = get_installation_access_token(installation.installation_id)
    except GitHubAppError:
        logger.warning(
            "Practices scanner could not mint installation token scan_id=%s",
            scan.pk,
        )
        return [
            RawFinding(
                title="Could not check branch protection (token error)",
                severity=Finding.Severity.INFO,
                category=Finding.Category.PRACTICE,
                summary=(
                    "The Lockfile could not mint a GitHub App installation token to "
                    "inspect branch protection for this repository."
                ),
                recommendation=(
                    "Confirm GITHUB_APP_ID and the App private key are configured on "
                    "the worker, and that the App installation is still active."
                ),
                rule_id="practice.token_error",
            )
        ]

    timeout = float(getattr(settings, "SCANNER_GITHUB_TIMEOUT_SECONDS", 20))
    status, data = _get_branch_protection(
        owner=owner,
        repo=name,
        branch=branch,
        token=token.token,
        timeout=timeout,
    )

    findings: list[RawFinding] = []

    if status == 404:
        findings.append(
            RawFinding(
                title=f"No branch protection on default branch ({branch})",
                severity=Finding.Severity.HIGH,
                category=Finding.Category.PRACTICE,
                summary=(
                    f"GitHub reports no branch protection rule for `{branch}` on "
                    f"{owner_repo}. Anyone with write access may push directly, force-push, "
                    "or merge without reviews."
                ),
                recommendation=(
                    f"In GitHub: Settings → Branches → Add rule for `{branch}`. "
                    "Require a pull request before merging, require at least one approving "
                    "review, and block force pushes. For teams, also require status checks "
                    "to pass before merge."
                ),
                rule_id="practice.no_branch_protection",
            )
        )
        budget.record_emit()
        return findings

    if status in (401, 403):
        findings.append(
            RawFinding(
                title="Branch protection could not be read (missing App permission)",
                severity=Finding.Severity.LOW,
                category=Finding.Category.PRACTICE,
                summary=(
                    f"The GitHub App could not read branch protection for `{branch}` on "
                    f"{owner_repo} (HTTP {status}). Practices checks need Administration: "
                    "Read-only (or the newer dedicated branch protection read permission)."
                ),
                recommendation=(
                    "Update the GitHub App permissions: Repository → Administration: "
                    "Read-only (covers branch protection reads). Then open the "
                    "installation on GitHub, accept the new permissions, and run "
                    "another scan. See Account settings for recovery links."
                ),
                rule_id="practice.permission_denied",
            )
        )
        return findings

    if status != 200 or not isinstance(data, dict):
        logger.warning(
            "Practices scanner unexpected status=%s scan_id=%s",
            status,
            scan.pk,
        )
        return [
            RawFinding(
                title="Branch protection check skipped due to API error",
                severity=Finding.Severity.INFO,
                category=Finding.Category.PRACTICE,
                summary=(
                    f"GitHub returned an unexpected response while reading protection "
                    f"for `{branch}` on {owner_repo}."
                ),
                recommendation=(
                    "Retry the scan later. If this persists, check GitHub API status "
                    "and App permissions."
                ),
                rule_id="practice.api_error",
            )
        ]

    # required_pull_request_reviews
    reviews = data.get("required_pull_request_reviews")
    if not reviews:
        if budget.can_emit():
            findings.append(
                RawFinding(
                    title="Pull request reviews are not required on the default branch",
                    severity=Finding.Severity.HIGH,
                    category=Finding.Category.PRACTICE,
                    summary=(
                        f"Branch protection exists on `{branch}`, but required pull request "
                        "reviews are not enabled. Changes can merge without a human review."
                    ),
                    recommendation=(
                        f"Edit the branch protection rule for `{branch}` and enable "
                        '"Require a pull request before merging" with at least one '
                        "approving review. Prefer dismissing stale reviews on new commits."
                    ),
                    rule_id="practice.no_required_reviews",
                )
            )
            budget.record_emit()
    else:
        count = int(reviews.get("required_approving_review_count") or 0)
        if count < 1 and budget.can_emit():
            findings.append(
                RawFinding(
                    title="Required approving review count is zero",
                    severity=Finding.Severity.MEDIUM,
                    category=Finding.Category.PRACTICE,
                    summary=(
                        f"`{branch}` has pull request review settings, but the required "
                        "approving review count is 0. Merges can proceed without approval."
                    ),
                    recommendation=(
                        "Set required approving reviews to at least 1 (2 for critical repos)."
                    ),
                    rule_id="practice.zero_review_count",
                )
            )
            budget.record_emit()

    checks = data.get("required_status_checks")
    if not checks and budget.can_emit():
        findings.append(
            RawFinding(
                title="No required status checks on the default branch",
                severity=Finding.Severity.MEDIUM,
                category=Finding.Category.PRACTICE,
                summary=(
                    f"`{branch}` does not require status checks to pass before merge. "
                    "Broken builds or skipped CI can still land on the default branch."
                ),
                recommendation=(
                    "Enable required status checks for your main CI job names (tests, lint, "
                    "security) on the branch protection rule."
                ),
                rule_id="practice.no_required_status_checks",
            )
        )
        budget.record_emit()

    allow_force = data.get("allow_force_pushes")
    if isinstance(allow_force, dict) and allow_force.get("enabled") and budget.can_emit():
        findings.append(
            RawFinding(
                title="Force pushes are allowed on the default branch",
                severity=Finding.Severity.HIGH,
                category=Finding.Category.PRACTICE,
                summary=(
                    f"`{branch}` allows force pushes. History can be rewritten, which "
                    "can hide changes and break downstream clones."
                ),
                recommendation=(
                    f"Disable force pushes on `{branch}` in the branch protection rule."
                ),
                rule_id="practice.allow_force_pushes",
            )
        )
        budget.record_emit()

    enforce_admins = data.get("enforce_admins")
    if isinstance(enforce_admins, dict) and not enforce_admins.get("enabled"):
        if budget.can_emit():
            findings.append(
                RawFinding(
                    title="Branch protection does not enforce rules for administrators",
                    severity=Finding.Severity.LOW,
                    category=Finding.Category.PRACTICE,
                    summary=(
                        f"Administrators can bypass protection on `{branch}`. Accidental "
                        "or compromised admin actions can skip reviews and checks."
                    ),
                    recommendation=(
                        'Enable "Do not allow bypassing the above settings" (enforce for admins) '
                        "on the branch protection rule."
                    ),
                    rule_id="practice.admins_can_bypass",
                )
            )
            budget.record_emit()

    logger.info("Practices scanner finished findings=%s", len(findings))
    return findings


def _get_branch_protection(
    *,
    owner: str,
    repo: str,
    branch: str,
    token: str,
    timeout: float,
) -> tuple[int, dict[str, Any] | None]:
    url = (
        f"https://api.github.com/repos/{urllib.parse.quote(owner)}/"
        f"{urllib.parse.quote(repo)}/branches/"
        f"{urllib.parse.quote(branch, safe='')}/protection"
    )
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            status = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except urllib.error.URLError:
        logger.warning("Practices scanner connection error for %s/%s", owner, repo)
        return 0, None

    try:
        parsed = json.loads(body) if body else {}
    except json.JSONDecodeError:
        return status, None
    if not isinstance(parsed, dict):
        return status, None
    return int(status), parsed
