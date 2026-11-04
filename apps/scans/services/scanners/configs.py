"""Heuristic insecure configuration checks (Docker, CI, app config)."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from apps.findings.models import Finding
from apps.scans.services.scanners.common import (
    iter_workspace_files,
    new_budget,
    read_text_file,
    rel_path,
    scanner_enabled,
)
from apps.scans.services.scanners.types import RawFinding

logger = logging.getLogger(__name__)

_FROM_LATEST = re.compile(
    r"(?im)^\s*FROM\s+(?:--platform=\S+\s+)?(\S+:latest)\s*(?:AS\s+\S+)?\s*$"
)
# Match FROM image without a tag or digest (and not scratch / variables).
_FROM_UNTAGGED = re.compile(
    r"(?im)^\s*FROM\s+(?:--platform=\S+\s+)?([a-z0-9][a-z0-9._\-/]*)\s*(?:AS\s+\S+)?\s*$"
)
_COMPOSE_LATEST = re.compile(
    r"(?im)^\s*image:\s*['\"]?([^\s'\"]+:latest)['\"]?\s*$"
)
_PERMISSIONS_WRITE_ALL = re.compile(
    r"(?im)^\s*permissions\s*:\s*write-all\s*$"
)
_PULL_REQUEST_TARGET = re.compile(
    r"(?im)^\s*pull_request_target\s*:"
)
_CHECKOUT_REF_PR = re.compile(
    r"(?im)uses:\s*actions/checkout@[^\s]+[\s\S]{0,200}?ref:\s*\$\{\{\s*github\.event\.pull_request"
)
_DEBUG_TRUE = re.compile(
    r"(?im)^\s*(?:DJANGO_DEBUG|DEBUG|NODE_ENV)\s*[=:]\s*(?:True|true|1|development)\s*$"
)
_PRIVILEGED = re.compile(r"(?im)^\s*privileged:\s*true\s*$")
_HOST_NETWORK = re.compile(r"(?im)^\s*network_mode:\s*['\"]?host['\"]?\s*$")


def scan_configs(*, workspace: Path) -> list[RawFinding]:
    if not scanner_enabled("SCANNER_ENABLE_CONFIGS", True):
        return []

    budget = new_budget()
    findings: list[RawFinding] = []
    seen: set[tuple[str, str]] = set()

    for path in iter_workspace_files(workspace, budget=budget):
        if not budget.can_emit():
            break
        name = path.name
        relative = rel_path(workspace, path)
        lower_rel = relative.lower()
        text = read_text_file(path)
        if text is None:
            continue

        is_dockerfile = name == "Dockerfile" or name.startswith("Dockerfile.")
        is_compose = name in {
            "docker-compose.yml",
            "docker-compose.yaml",
            "compose.yml",
            "compose.yaml",
        } or "docker-compose" in name.lower()
        is_gha = "/.github/workflows/" in f"/{lower_rel}" or lower_rel.startswith(
            ".github/workflows/"
        )
        is_envish = name.startswith(".env") or name in {"settings.py", "config.py"}

        if is_dockerfile:
            _check_dockerfile(text, relative, findings, seen, budget)
        if is_compose:
            _check_compose(text, relative, findings, seen, budget)
        if is_gha:
            _check_github_actions(text, relative, findings, seen, budget)
        if is_envish and name != "settings.py":
            _check_debug_env(text, relative, findings, seen, budget)
        # Django settings DEBUG = True (not in comments-only)
        if name == "settings.py" or lower_rel.endswith("/settings.py"):
            _check_django_debug(text, relative, findings, seen, budget)

    logger.info("Configs scanner finished findings=%s", len(findings))
    return findings


def _emit(
    findings: list[RawFinding],
    seen: set[tuple[str, str]],
    budget,
    *,
    rule_id: str,
    file_path: str,
    title: str,
    severity: str,
    summary: str,
    recommendation: str,
) -> None:
    if not budget.can_emit():
        return
    key = (rule_id, file_path)
    if key in seen:
        return
    seen.add(key)
    findings.append(
        RawFinding(
            title=title,
            severity=severity,
            category=Finding.Category.CONFIG,
            summary=summary,
            recommendation=recommendation,
            file_path=file_path,
            rule_id=rule_id,
        )
    )
    budget.record_emit()


def _check_dockerfile(
    text: str,
    relative: str,
    findings: list[RawFinding],
    seen: set[tuple[str, str]],
    budget,
) -> None:
    for match in _FROM_LATEST.finditer(text):
        image = match.group(1)
        _emit(
            findings,
            seen,
            budget,
            rule_id="config.docker_latest_tag",
            file_path=relative,
            title="Docker image uses the floating :latest tag",
            severity=Finding.Severity.MEDIUM,
            summary=(
                f"{relative} pulls `{image}`. The :latest tag can change without "
                "notice, so builds become non-reproducible and may suddenly include "
                "unreviewed changes or regressions."
            ),
            recommendation=(
                "Pin the base image to an immutable digest "
                "(`image@sha256:...`) or at least a specific version tag you "
                "control. Update the pin deliberately when you are ready to upgrade."
            ),
        )
        break

    for match in _FROM_UNTAGGED.finditer(text):
        image = match.group(1)
        if ":" in image or "@" in image:
            continue
        if image.lower() in {"scratch"} or image.startswith("$"):
            continue
        _emit(
            findings,
            seen,
            budget,
            rule_id="config.docker_unpinned_tag",
            file_path=relative,
            title="Docker base image is not pinned to a tag or digest",
            severity=Finding.Severity.MEDIUM,
            summary=(
                f"{relative} uses `FROM {image}` without a version tag or digest. "
                "Unpinned images resolve to whatever the registry considers current, "
                "which makes builds hard to reproduce and audit."
            ),
            recommendation=(
                f"Change the line to pin a version, for example `FROM {image}:<version>` "
                "or `FROM {image}@sha256:<digest>`, and update that pin on purpose."
            ),
        )
        break


def _check_compose(
    text: str,
    relative: str,
    findings: list[RawFinding],
    seen: set[tuple[str, str]],
    budget,
) -> None:
    if _COMPOSE_LATEST.search(text):
        _emit(
            findings,
            seen,
            budget,
            rule_id="config.compose_latest_tag",
            file_path=relative,
            title="Compose service uses an image: ...:latest tag",
            severity=Finding.Severity.MEDIUM,
            summary=(
                f"{relative} references an image tagged :latest. Floating tags make "
                "deployments non-reproducible and can introduce unexpected changes."
            ),
            recommendation=(
                "Replace :latest with a specific version tag or digest for each service "
                "image, and bump versions through a reviewed change."
            ),
        )
    if _PRIVILEGED.search(text):
        _emit(
            findings,
            seen,
            budget,
            rule_id="config.compose_privileged",
            file_path=relative,
            title="Compose service runs with privileged: true",
            severity=Finding.Severity.HIGH,
            summary=(
                f"{relative} sets privileged mode. Privileged containers can access "
                "host devices and weaken container isolation."
            ),
            recommendation=(
                "Remove privileged: true unless there is a documented, unavoidable need. "
                "Prefer granting the specific capabilities required instead."
            ),
        )
    if _HOST_NETWORK.search(text):
        _emit(
            findings,
            seen,
            budget,
            rule_id="config.compose_host_network",
            file_path=relative,
            title="Compose service uses host networking",
            severity=Finding.Severity.MEDIUM,
            summary=(
                f"{relative} sets network_mode: host, which shares the host network "
                "stack with the container and reduces network isolation."
            ),
            recommendation=(
                "Use bridge networking and published ports unless host networking is "
                "strictly required. Document the exception if you must keep it."
            ),
        )


def _check_github_actions(
    text: str,
    relative: str,
    findings: list[RawFinding],
    seen: set[tuple[str, str]],
    budget,
) -> None:
    if _PERMISSIONS_WRITE_ALL.search(text):
        _emit(
            findings,
            seen,
            budget,
            rule_id="config.gha_write_all",
            file_path=relative,
            title="GitHub Actions workflow grants permissions: write-all",
            severity=Finding.Severity.HIGH,
            summary=(
                f"{relative} sets permissions: write-all, so every job gets broad write "
                "access to the repository and related scopes. A compromised workflow "
                "step could change code, releases, or packages."
            ),
            recommendation=(
                "Set a minimal top-level permissions block (often contents: read) and "
                "grant write only on the specific jobs that need it."
            ),
        )
    if _PULL_REQUEST_TARGET.search(text) and _CHECKOUT_REF_PR.search(text):
        _emit(
            findings,
            seen,
            budget,
            rule_id="config.gha_pull_request_target_checkout",
            file_path=relative,
            title="pull_request_target checks out untrusted pull request code",
            severity=Finding.Severity.CRITICAL,
            summary=(
                f"{relative} uses pull_request_target and checks out the pull request "
                "head. That combination runs potentially untrusted code with the base "
                "repository's secrets, which is a common supply-chain foothold."
            ),
            recommendation=(
                "Prefer the pull_request event for CI that builds or tests PR code. "
                "If pull_request_target is required, do not check out or execute PR "
                "code in the same job that has secrets. Split trust boundaries carefully."
            ),
        )


def _check_debug_env(
    text: str,
    relative: str,
    findings: list[RawFinding],
    seen: set[tuple[str, str]],
    budget,
) -> None:
    # Only flag committed .env files that enable debug/development.
    if not relative.startswith(".env") and "/.env" not in f"/{relative}":
        return
    if relative.endswith(".example") or relative.endswith(".sample"):
        return
    if _DEBUG_TRUE.search(text):
        _emit(
            findings,
            seen,
            budget,
            rule_id="config.env_debug_enabled",
            file_path=relative,
            title="Debug or development mode enabled in a committed env file",
            severity=Finding.Severity.MEDIUM,
            summary=(
                f"{relative} turns on debug/development settings. If this file is used "
                "in a shared or production-like environment, it can expose verbose "
                "errors and weaken hardening."
            ),
            recommendation=(
                "Keep production env files out of git, set DEBUG/DJANGO_DEBUG off for "
                "deployed environments, and use .env.example with placeholders only."
            ),
        )


def _check_django_debug(
    text: str,
    relative: str,
    findings: list[RawFinding],
    seen: set[tuple[str, str]],
    budget,
) -> None:
    if re.search(r"(?m)^\s*DEBUG\s*=\s*True\b", text):
        _emit(
            findings,
            seen,
            budget,
            rule_id="config.django_debug_true",
            file_path=relative,
            title="Django DEBUG is hard-coded to True",
            severity=Finding.Severity.MEDIUM,
            summary=(
                f"{relative} sets DEBUG = True directly. Debug mode can leak "
                "sensitive tracebacks and is unsafe for production."
            ),
            recommendation=(
                "Drive DEBUG from an environment variable with a safe default of False, "
                "and never ship DEBUG = True for production settings."
            ),
        )
