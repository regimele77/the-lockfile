"""Heuristic CI/CD workflow gap checks."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from apps.findings.models import Finding
from apps.scans.services.scanners.common import (
    new_budget,
    read_text_file,
    rel_path,
    scanner_enabled,
)
from apps.scans.services.scanners.types import RawFinding

logger = logging.getLogger(__name__)

_ON_PUSH = re.compile(r"(?im)^\s*push\s*:")
_ON_PULL_REQUEST = re.compile(r"(?im)^\s*pull_request\s*:")
_ON_WORKFLOW_DISPATCH = re.compile(r"(?im)^\s*workflow_dispatch\s*:")
_TEST_HINT = re.compile(
    r"(?i)\b(pytest|npm test|yarn test|pnpm test|go test|cargo test|"
    r"mvn test|gradle test|rspec|phpunit|tox|unittest|jest|vitest|"
    r"cypress|playwright)\b"
)
_JOB_RUNS_TESTISH = re.compile(
    r"(?im)^\s*(?:name|id)\s*:\s*.*\b(test|lint|check|ci|build|verify)\b"
)
_ECHO_SECRET = re.compile(
    r"(?i)(?:echo|print|printf|Write-Host).{0,40}\$\{\{\s*secrets\."
)


def scan_workflows(*, workspace: Path) -> list[RawFinding]:
    if not scanner_enabled("SCANNER_ENABLE_WORKFLOWS", True):
        return []

    budget = new_budget()
    workflows_dir = workspace / ".github" / "workflows"
    findings: list[RawFinding] = []

    if not workflows_dir.is_dir():
        # Also peek at other common CI configs for a softer signal.
        other_ci = _find_other_ci(workspace)
        if other_ci:
            logger.info("No GitHub workflows; found other CI at %s", other_ci)
            return findings
        findings.append(
            RawFinding(
                title="No GitHub Actions workflows found",
                severity=Finding.Severity.MEDIUM,
                category=Finding.Category.WORKFLOW,
                summary=(
                    "This repository has no `.github/workflows` directory. Without CI "
                    "on the default branch, broken or unsafe changes can reach the main "
                    "line without automated checks."
                ),
                recommendation=(
                    "Add a GitHub Actions workflow that runs tests (and lint/security "
                    "checks if you have them) on pull_request and on push to the default "
                    "branch. Keep permissions minimal."
                ),
                file_path=".github/workflows",
                rule_id="workflow.missing_gha",
            )
        )
        return findings

    workflow_files = sorted(
        p
        for p in workflows_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".yml", ".yaml"}
    )
    if not workflow_files:
        findings.append(
            RawFinding(
                title="GitHub Actions workflows directory is empty",
                severity=Finding.Severity.MEDIUM,
                category=Finding.Category.WORKFLOW,
                summary=(
                    "`.github/workflows` exists but contains no YAML workflow files, so "
                    "GitHub Actions will not run checks on changes."
                ),
                recommendation=(
                    "Add at least one workflow that runs on pull requests and pushes to "
                    "the default branch."
                ),
                file_path=".github/workflows",
                rule_id="workflow.empty_gha_dir",
            )
        )
        return findings

    any_pr_or_push = False
    any_testish = False
    dispatch_only = True

    for path in workflow_files:
        if not budget.can_emit():
            break
        text = read_text_file(path)
        if text is None:
            continue
        relative = rel_path(workspace, path)
        has_push = bool(_ON_PUSH.search(text))
        has_pr = bool(_ON_PULL_REQUEST.search(text))
        has_dispatch = bool(_ON_WORKFLOW_DISPATCH.search(text))
        if has_push or has_pr:
            any_pr_or_push = True
            dispatch_only = False
        elif has_dispatch and not (has_push or has_pr):
            pass
        else:
            dispatch_only = False

        if _TEST_HINT.search(text) or _JOB_RUNS_TESTISH.search(text):
            any_testish = True

        if _ECHO_SECRET.search(text) and budget.can_emit():
            findings.append(
                RawFinding(
                    title="Workflow may print GitHub secrets to logs",
                    severity=Finding.Severity.HIGH,
                    category=Finding.Category.WORKFLOW,
                    summary=(
                        f"{relative} appears to echo or print a `secrets.*` value. "
                        "Secret values in logs can leak to anyone with Actions log access."
                    ),
                    recommendation=(
                        "Never echo secrets. Pass them only as env vars to trusted actions "
                        "or commands, and rely on GitHub's secret masking without printing."
                    ),
                    file_path=relative,
                    rule_id="workflow.echo_secret",
                )
            )
            budget.record_emit()

        # Deploy-like job without environment protection
        if re.search(r"(?im)^\s*deploy\s*:", text) or re.search(
            r"(?i)\b(deploy|release|production)\b", text
        ):
            if "environment:" not in text.lower() and budget.can_emit():
                # Only flag if it looks like a deploy workflow, not every mention.
                if re.search(r"(?im)^\s*jobs\s*:", text) and re.search(
                    r"(?i)(deploy|release|production)", Path(relative).stem
                ):
                    findings.append(
                        RawFinding(
                            title="Deploy-style workflow has no GitHub Environment",
                            severity=Finding.Severity.MEDIUM,
                            category=Finding.Category.WORKFLOW,
                            summary=(
                                f"{relative} looks like a deploy/release workflow but does "
                                "not declare a GitHub `environment:`. Environments can "
                                "require reviewers and restrict secrets for production."
                            ),
                            recommendation=(
                                "Create a GitHub Environment (for example `production`) with "
                                "required reviewers, then set `environment: production` on "
                                "the deploy job."
                            ),
                            file_path=relative,
                            rule_id="workflow.deploy_without_environment",
                        )
                    )
                    budget.record_emit()

    if dispatch_only and not any_pr_or_push and budget.can_emit():
        findings.append(
            RawFinding(
                title="Workflows only run via manual workflow_dispatch",
                severity=Finding.Severity.MEDIUM,
                category=Finding.Category.WORKFLOW,
                summary=(
                    "Existing GitHub Actions workflows appear to run only when someone "
                    "starts them manually. Pull requests and default-branch pushes may "
                    "reach the tree without automated checks."
                ),
                recommendation=(
                    "Add `pull_request` and `push` triggers (scoped to the default branch) "
                    "so tests run on every proposed change, not only when someone remembers "
                    "to click Run workflow."
                ),
                file_path=".github/workflows",
                rule_id="workflow.dispatch_only",
            )
        )
        budget.record_emit()

    if any_pr_or_push and not any_testish and budget.can_emit():
        findings.append(
            RawFinding(
                title="CI workflows do not appear to run tests",
                severity=Finding.Severity.LOW,
                category=Finding.Category.WORKFLOW,
                summary=(
                    "Workflows trigger on push or pull_request, but none clearly run a "
                    "common test command or a job named like test/lint/check. Code may "
                    "merge without automated verification."
                ),
                recommendation=(
                    "Add a job that runs your test suite (and lint if available) on every "
                    "pull request. Name the job clearly and require it as a status check."
                ),
                file_path=".github/workflows",
                rule_id="workflow.no_tests_detected",
            )
        )
        budget.record_emit()

    if not any_pr_or_push and not dispatch_only and budget.can_emit():
        # Workflows exist but neither push/PR nor only-dispatch patterns matched cleanly.
        findings.append(
            RawFinding(
                title="No push or pull_request triggers detected in workflows",
                severity=Finding.Severity.MEDIUM,
                category=Finding.Category.WORKFLOW,
                summary=(
                    "Workflow YAML files exist, but none clearly trigger on `push` or "
                    "`pull_request`. Changes may reach the default branch without CI."
                ),
                recommendation=(
                    "Ensure at least one workflow runs on pull requests and on pushes to "
                    "the default branch."
                ),
                file_path=".github/workflows",
                rule_id="workflow.no_pr_push_triggers",
            )
        )
        budget.record_emit()

    logger.info("Workflows scanner finished findings=%s", len(findings))
    return findings


def _find_other_ci(workspace: Path) -> str | None:
    candidates = [
        ".gitlab-ci.yml",
        ".circleci/config.yml",
        "bitbucket-pipelines.yml",
        "azure-pipelines.yml",
        "Jenkinsfile",
        ".travis.yml",
    ]
    for rel in candidates:
        path = workspace / rel
        if path.is_file():
            return rel
    return None
