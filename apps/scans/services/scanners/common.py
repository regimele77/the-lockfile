"""Shared helpers for workspace walking, limits, and redaction."""

from __future__ import annotations

import logging
import re
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from django.conf import settings

from apps.core.services import technical_config as tech

logger = logging.getLogger(__name__)

SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".tox",
        ".venv",
        "venv",
        "node_modules",
        "bower_components",
        "vendor",
        "dist",
        "build",
        "coverage",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".next",
        ".nuxt",
        ".turbo",
        "target",
        "Pods",
        "Carthage",
        ".gradle",
        ".idea",
        ".vscode",
    }
)

SKIP_FILE_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".svg",
        ".pdf",
        ".zip",
        ".gz",
        ".tar",
        ".tgz",
        ".bz2",
        ".7z",
        ".rar",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".mp3",
        ".mp4",
        ".webm",
        ".mov",
        ".avi",
        ".class",
        ".o",
        ".so",
        ".dylib",
        ".dll",
        ".exe",
        ".bin",
        ".pyc",
        ".pyo",
        ".wasm",
        ".lock",  # binary-ish lock formats handled by dedicated parsers
    }
)

# Yarn/Cargo/Gemfile lockfiles are text; allow those by name override.
TEXT_LOCKFILE_NAMES = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "Pipfile.lock",
        "Cargo.lock",
        "Gemfile.lock",
        "composer.lock",
        "go.sum",
    }
)

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class ScannerBudget:
    """Soft time and count budget for one scanner run."""

    def __init__(self, *, timeout_seconds: float, max_findings: int) -> None:
        self.deadline = time.monotonic() + max(5.0, timeout_seconds)
        self.max_findings = max(1, max_findings)
        self.findings_emitted = 0

    def expired(self) -> bool:
        return time.monotonic() >= self.deadline

    def can_emit(self) -> bool:
        return self.findings_emitted < self.max_findings and not self.expired()

    def record_emit(self) -> None:
        self.findings_emitted += 1


def scanner_timeout_seconds() -> float:
    return tech.scanner_timeout_seconds()


def scanner_max_findings() -> int:
    return tech.max_findings_per_scanner()


def max_file_bytes() -> int:
    return tech.max_file_bytes()


def max_files() -> int:
    return tech.max_files()


def new_budget() -> ScannerBudget:
    return ScannerBudget(
        timeout_seconds=scanner_timeout_seconds(),
        max_findings=scanner_max_findings(),
    )


def ensure_inside_workspace(workspace: Path, path: Path) -> Path | None:
    """Return resolved path if it stays under workspace, else None."""
    try:
        workspace_resolved = workspace.resolve()
        candidate = path.resolve()
    except OSError:
        return None
    try:
        candidate.relative_to(workspace_resolved)
    except ValueError:
        logger.warning("Skipped path outside workspace: %s", path)
        return None
    return candidate


def rel_path(workspace: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(workspace.resolve()).as_posix()
    except (OSError, ValueError):
        return path.name


def path_in_git_head(workspace: Path, relative_path: str) -> bool:
    """
    Return True when relative_path exists in HEAD (file or tree).

    Used to avoid GitHub blob/tree links that 404 for gitignored, local-only,
    or otherwise untracked paths (for example a local `.env`).
    """
    rel = (relative_path or "").strip().lstrip("/")
    if not rel or ".." in PurePosixPath(rel).parts:
        return False
    if not (workspace / ".git").exists():
        return False
    try:
        completed = subprocess.run(
            ["git", "cat-file", "-e", f"HEAD:{rel}"],
            cwd=str(workspace),
            check=False,
            capture_output=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    return completed.returncode == 0


def iter_workspace_files(
    workspace: Path,
    *,
    budget: ScannerBudget | None = None,
    suffixes: frozenset[str] | None = None,
    names: frozenset[str] | None = None,
    max_bytes: int | None = None,
) -> Iterator[Path]:
    """
    Yield text-ish files under workspace with skip rules and size/count caps.

    Never follows paths outside the workspace root.
    """
    root = ensure_inside_workspace(workspace, workspace)
    if root is None or not root.is_dir():
        return

    file_limit = max_files()
    size_limit = max_bytes if max_bytes is not None else max_file_bytes()
    seen = 0

    for dirpath, dirnames, filenames in _safe_walk(root):
        if budget is not None and budget.expired():
            return
        # Prune skip dirs in-place.
        dirnames[:] = sorted(
            d for d in dirnames if d not in SKIP_DIR_NAMES and not d.startswith(".git")
        )
        current = Path(dirpath)
        for name in sorted(filenames):
            if budget is not None and budget.expired():
                return
            if seen >= file_limit:
                return
            if names is not None and name not in names:
                continue
            path = current / name
            if suffixes is not None:
                if path.suffix.lower() not in suffixes and name not in TEXT_LOCKFILE_NAMES:
                    continue
            elif _should_skip_file(name, path):
                continue
            try:
                if not path.is_file() or path.is_symlink():
                    continue
                if path.stat().st_size > size_limit:
                    continue
            except OSError:
                continue
            if ensure_inside_workspace(workspace, path) is None:
                continue
            seen += 1
            yield path


def _safe_walk(root: Path):
    try:
        yield from root.walk(top_down=True, follow_symlinks=False)  # type: ignore[attr-defined]
    except AttributeError:
        # Python < 3.12 Path.walk fallback
        import os

        for dirpath, dirnames, filenames in os.walk(
            root, topdown=True, followlinks=False
        ):
            yield Path(dirpath), dirnames, filenames


def _should_skip_file(name: str, path: Path) -> bool:
    if name in TEXT_LOCKFILE_NAMES:
        return False
    lower = name.lower()
    if lower.endswith(tuple(SKIP_FILE_SUFFIXES)):
        return True
    # Skip huge minified bundles by name pattern.
    if lower.endswith((".min.js", ".min.css", ".map")):
        return True
    return False


def read_text_file(path: Path, *, max_bytes: int | None = None) -> str | None:
    """Read a file as UTF-8 text, skipping obvious binary content."""
    limit = max_bytes if max_bytes is not None else max_file_bytes()
    try:
        raw = path.read_bytes()[: limit + 1]
    except OSError:
        return None
    if len(raw) > limit:
        raw = raw[:limit]
    if b"\x00" in raw[:8192]:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("latin-1")
        except UnicodeDecodeError:
            return None
    if _CONTROL_CHARS.search(text[:4096]):
        # Allow tabs/newlines only; reject other controls as binary-ish.
        sample = text[:4096].replace("\t", "").replace("\n", "").replace("\r", "")
        if _CONTROL_CHARS.search(sample):
            return None
    return text


def redact_secret(value: str, *, keep_tail: int = 4) -> str:
    """Never store a full secret. Keep a short tail when long enough."""
    cleaned = value.strip()
    if len(cleaned) <= keep_tail + 2:
        return "[redacted]"
    return f"[redacted]...{cleaned[-keep_tail:]}"


def scanner_enabled(flag_name: str, default: bool = True) -> bool:
    return bool(getattr(settings, flag_name, default))
