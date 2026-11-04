"""Detect exposed secrets in the working tree."""

from __future__ import annotations

import logging
import math
import re
from pathlib import Path

from apps.findings.models import Finding
from apps.scans.services.scanners.common import (
    iter_workspace_files,
    new_budget,
    read_text_file,
    redact_secret,
    rel_path,
    scanner_enabled,
)
from apps.scans.services.scanners.types import RawFinding

logger = logging.getLogger(__name__)

# High-signal credential patterns. Values are never stored in full.
_RULES: list[tuple[str, re.Pattern[str], str, str]] = [
    (
        "aws_access_key",
        re.compile(r"(?<![A-Z0-9])(AKIA[0-9A-Z]{16})(?![A-Z0-9])"),
        "AWS access key ID found in source",
        Finding.Severity.CRITICAL,
    ),
    (
        "github_pat",
        re.compile(r"(gh[pousr]_[A-Za-z0-9_]{36,}|github_pat_[A-Za-z0-9_]{20,})"),
        "GitHub personal access token found in source",
        Finding.Severity.CRITICAL,
    ),
    (
        "slack_token",
        re.compile(r"(xox[baprs]-[0-9A-Za-z-]{10,})"),
        "Slack API token found in source",
        Finding.Severity.HIGH,
    ),
    (
        "stripe_secret",
        re.compile(r"(sk_live_[0-9A-Za-z]{24,})"),
        "Stripe live secret key found in source",
        Finding.Severity.CRITICAL,
    ),
    (
        "google_api_key",
        re.compile(r"(AIza[0-9A-Za-z\-_]{35})"),
        "Google API key found in source",
        Finding.Severity.HIGH,
    ),
    (
        "private_key_block",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
        ),
        "Private key material found in source",
        Finding.Severity.CRITICAL,
    ),
    (
        "generic_bearer",
        re.compile(
            r"(?i)(?:authorization|api[_-]?key|secret|token|password)\s*[:=]\s*"
            r"['\"]?(Bearer\s+[A-Za-z0-9\-._~+/]+=*|sk-[A-Za-z0-9]{20,})"
            r"['\"]?"
        ),
        "Likely API credential assigned in source",
        Finding.Severity.HIGH,
    ),
]

_ASSIGNMENT = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|secret[_-]?key|auth[_-]?token|"
    r"client[_-]?secret|private[_-]?key)\s*[:=]\s*['\"]([^'\"]{20,})['\"]"
)

_HEX_OR_B64 = re.compile(r"^[A-Za-z0-9+/=_\-]{24,}$")

_SCAN_SUFFIXES = frozenset(
    {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".rb",
        ".go",
        ".java",
        ".kt",
        ".rs",
        ".php",
        ".cs",
        ".env",
        ".yml",
        ".yaml",
        ".json",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".properties",
        ".xml",
        ".sh",
        ".bash",
        ".zsh",
        ".ps1",
        ".tf",
        ".hcl",
        ".md",
        ".txt",
        ".html",
        ".vue",
        ".svelte",
    }
)

_SCAN_NAMES = frozenset(
    {
        "Dockerfile",
        "dockerfile",
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        "id_rsa",
        "id_ed25519",
        "credentials",
    }
)


def scan_secrets(*, workspace: Path) -> list[RawFinding]:
    if not scanner_enabled("SCANNER_ENABLE_SECRETS", True):
        return []

    budget = new_budget()
    findings: list[RawFinding] = []
    seen: set[tuple[str, str]] = set()

    for path in iter_workspace_files(workspace, budget=budget):
        if not budget.can_emit():
            break
        name = path.name
        suffix = path.suffix.lower()
        if name not in _SCAN_NAMES and suffix not in _SCAN_SUFFIXES:
            if not name.startswith(".env"):
                continue
        text = read_text_file(path)
        if not text:
            continue
        relative = rel_path(workspace, path)
        for rule_id, pattern, title, severity in _RULES:
            if not budget.can_emit():
                break
            for match in pattern.finditer(text):
                if not budget.can_emit():
                    break
                secret = match.group(1) if match.lastindex else match.group(0)
                if secret in _KNOWN_DUMMY_SECRETS or "EXAMPLE" in secret:
                    continue
                key = (rule_id, relative)
                if key in seen:
                    break
                seen.add(key)
                redacted = redact_secret(secret)
                findings.append(
                    RawFinding(
                        title=title,
                        severity=severity,
                        category=Finding.Category.SECRET,
                        summary=(
                            f"A credential matching a known secret pattern was found in "
                            f"{relative}. Exposed secrets can be abused by anyone with "
                            f"repo access or a leaked copy. Value shown redacted: {redacted}."
                        ),
                        recommendation=(
                            "1. Rotate or revoke this credential immediately in the "
                            "provider console.\n"
                            "2. Remove it from the repository and replace it with an "
                            "environment variable or a secrets manager.\n"
                            "3. Check git history for earlier commits of the same value "
                            "and rotate those too if present.\n"
                            "4. Add the file pattern to .gitignore if it should stay local."
                        ),
                        file_path=relative,
                        rule_id=f"secret.{rule_id}",
                    )
                )
                budget.record_emit()
                break  # one hit per rule per file

        if not budget.can_emit():
            break
        for match in _ASSIGNMENT.finditer(text):
            if not budget.can_emit():
                break
            value = match.group(1)
            if not _looks_like_secret(value):
                continue
            key = ("high_entropy_assignment", relative)
            if key in seen:
                break
            seen.add(key)
            findings.append(
                RawFinding(
                    title="High-entropy secret-like value assigned in source",
                    severity=Finding.Severity.HIGH,
                    category=Finding.Category.SECRET,
                    summary=(
                        f"A variable name that usually holds a secret is assigned a "
                        f"long, random-looking value in {relative}. Redacted value: "
                        f"{redact_secret(value)}. If this is a real credential, it "
                        f"should not live in the working tree."
                    ),
                    recommendation=(
                        "Move the value to a secret store or environment variable, "
                        "rotate it if it was ever committed, and keep only a placeholder "
                        "or reference in source control."
                    ),
                    file_path=relative,
                    rule_id="secret.high_entropy_assignment",
                )
            )
            budget.record_emit()
            break

    logger.info("Secrets scanner finished findings=%s", len(findings))
    return findings


_KNOWN_DUMMY_SECRETS = frozenset(
    {
        "AKIAIOSFODNN7EXAMPLE",
        "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    }
)


def _looks_like_secret(value: str) -> bool:
    if len(value) < 24:
        return False
    if value in _KNOWN_DUMMY_SECRETS:
        return False
    lowered = value.lower()
    if any(
        marker in lowered
        for marker in (
            "example",
            "changeme",
            "placeholder",
            "your_",
            "xxx",
            "todo",
            "sample",
        )
    ):
        return False
    if not _HEX_OR_B64.match(value):
        return False
    return _shannon_entropy(value) >= 3.5


def _shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for ch in value:
        counts[ch] = counts.get(ch, 0) + 1
    length = len(value)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())
