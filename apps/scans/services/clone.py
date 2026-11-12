"""Secure shallow clone of a GitHub repository into a scan workspace."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from apps.core.services import technical_config as tech
from apps.scans.services.sanitize import sanitize_error_message

logger = logging.getLogger(__name__)

_REPO_FULL_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


class CloneError(Exception):
    """Raised when a repository cannot be cloned safely."""


@dataclass(frozen=True)
class CloneResult:
    workspace: Path
    commit_sha: str
    default_branch: str


def workspace_root() -> Path:
    root = Path(settings.SCAN_WORKSPACE_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    return root


def prepare_scan_workspace(scan_id: int) -> Path:
    """Create a unique empty directory for one scan."""
    path = workspace_root() / f"scan-{int(scan_id)}"
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=False)
    return path


def cleanup_workspace(path: Path | None) -> None:
    if path is None:
        return
    try:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    except OSError:
        logger.warning("Failed to remove scan workspace path=%s", path)


def clone_repository(
    *,
    full_name: str,
    access_token: str,
    destination: Path,
) -> CloneResult:
    """
    Shallow-clone the default branch into destination using an installation token.

    Auth prefers GIT_CONFIG_* so the token is not present in process argv.
    Falls back to an x-access-token HTTPS URL if needed. Never log the token.
    """
    if not _REPO_FULL_NAME_RE.fullmatch(full_name):
        raise CloneError("Repository full name is invalid.")
    if not access_token:
        raise CloneError("Missing installation access token.")
    if destination.exists() and any(destination.iterdir()):
        raise CloneError("Clone destination is not empty.")

    destination.mkdir(parents=True, exist_ok=True)
    public_url = f"https://github.com/{full_name}.git"
    depth = tech.clone_depth()
    timeout = tech.clone_timeout_seconds()

    logger.info(
        "Cloning repository full_name=%s depth=%s timeout=%s",
        full_name,
        depth,
        timeout,
    )

    # First attempt: Authorization header via git config env (token not in argv).
    header_env = _git_env(
        {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.extraHeader",
            "GIT_CONFIG_VALUE_0": f"Authorization: Bearer {access_token}",
        }
    )
    result = _run_clone(
        url=public_url,
        destination=destination,
        depth=depth,
        timeout=timeout,
        env=header_env,
    )
    if result.returncode != 0:
        # Fallback used by GitHub App docs: x-access-token in the URL.
        # Token may appear in git stderr; sanitize before surfacing.
        if destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
            destination.mkdir(parents=True, exist_ok=True)
        authed_url = f"https://x-access-token:{access_token}@github.com/{full_name}.git"
        result = _run_clone(
            url=authed_url,
            destination=destination,
            depth=depth,
            timeout=timeout,
            env=_git_env({}),
        )

    if result.returncode != 0:
        detail = sanitize_error_message(
            (result.stderr or result.stdout or "").strip()
        )
        if not detail:
            detail = (
                "git returned a non-zero exit code. "
                "Ensure the App has Contents: Read, is installed on this repo, "
                "and the repo is still in the installation selection."
            )
        # Prefer a stable permission message when git stderr looks like auth denial.
        lowered = detail.lower()
        if any(
            marker in lowered
            for marker in (
                "authentication failed",
                "could not read username",
                "repository not found",
                "permission denied",
                "write access to repository not granted",
            )
        ):
            raise CloneError(
                "Clone failed: permission denied. Confirm Contents: Read, "
                "that the App is installed on this repository, and refresh "
                "repositories if the repo was removed from the installation."
            )
        raise CloneError(f"Clone failed: {detail}")

    _enforce_size_limit(destination)
    commit_sha = _git_output(["rev-parse", "HEAD"], destination)
    default_branch = _detect_default_branch(destination)
    return CloneResult(
        workspace=destination,
        commit_sha=commit_sha,
        default_branch=default_branch,
    )


def _git_env(extra: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    env.update(extra)
    return env


def _run_clone(
    *,
    url: str,
    destination: Path,
    depth: int,
    timeout: int,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    cmd = [
        "git",
        "clone",
        "--depth",
        str(depth),
        "--single-branch",
        url,
        str(destination),
    ]
    try:
        return subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError as exc:
        raise CloneError(
            "git is not installed in this environment. Install git on the worker image."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise CloneError(
            f"Clone timed out after {timeout} seconds. Try a smaller repository "
            "or raise the clone timeout in Account settings."
        ) from exc


def _enforce_size_limit(path: Path) -> None:
    max_mb = tech.max_repo_size_mb()
    if max_mb <= 0:
        return
    max_bytes = max_mb * 1024 * 1024
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
            if total > max_bytes:
                raise CloneError(
                    f"Cloned repository exceeds the size limit of {max_mb} MB. "
                    "Raise max repository size in Account settings if this repo "
                    "should be allowed."
                )


def _detect_default_branch(repo_path: Path) -> str:
    try:
        ref = _git_output(["symbolic-ref", "--short", "HEAD"], repo_path)
        if ref:
            return ref
    except CloneError:
        pass
    try:
        return _git_output(["rev-parse", "--abbrev-ref", "HEAD"], repo_path)
    except CloneError:
        return ""


def _git_output(args: list[str], cwd: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(cwd),
            env=_git_env({}),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise CloneError("Could not inspect the cloned repository.") from exc
    if completed.returncode != 0:
        detail = sanitize_error_message((completed.stderr or "").strip())
        raise CloneError(detail or "git inspect failed.")
    return (completed.stdout or "").strip()
