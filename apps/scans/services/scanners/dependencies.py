"""Find vulnerable dependencies via manifests/lockfiles and the OSV API."""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from apps.findings.models import Finding
from apps.scans.services.scanners.common import (
    new_budget,
    read_text_file,
    rel_path,
    scanner_enabled,
)
from apps.scans.services.scanners.types import RawFinding

logger = logging.getLogger(__name__)

OSV_QUERYBATCH_URL = "https://api.osv.dev/v1/querybatch"
USER_AGENT = "the-lockfile"

_REQ_LINE = re.compile(
    r"^\s*([A-Za-z0-9_.\-]+)\s*==\s*([A-Za-z0-9_.\-]+)\s*(?:#.*)?$"
)
_GO_REQUIRE = re.compile(
    r"^\s*([A-Za-z0-9.\-_/]+)\s+v([0-9][A-Za-z0-9.\-+]*)\s*$"
)
_CARGO_NAME = re.compile(r'^name\s*=\s*"([^"]+)"\s*$')
_CARGO_VERSION = re.compile(r'^version\s*=\s*"([^"]+)"\s*$')

_MANIFEST_NAMES = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "requirements.txt",
        "poetry.lock",
        "Pipfile.lock",
        "go.mod",
        "Cargo.lock",
        "Gemfile.lock",
    }
)


@dataclass(frozen=True)
class PackageRef:
    name: str
    version: str
    ecosystem: str
    file_path: str


def scan_dependencies(*, workspace: Path) -> list[RawFinding]:
    if not scanner_enabled("SCANNER_ENABLE_DEPENDENCIES", True):
        return []

    budget = new_budget()
    packages = _collect_packages(workspace, budget=budget)
    if not packages:
        logger.info("Dependencies scanner found no parseable packages")
        return []

    # Cap advisory lookups.
    max_query = int(getattr(settings, "SCANNER_OSV_MAX_PACKAGES", 200))
    packages = packages[: max(1, max_query)]

    if not scanner_enabled("SCANNER_OSV_ENABLED", True):
        return [
            RawFinding(
                title="Dependency manifests found but advisory lookup is disabled",
                severity=Finding.Severity.INFO,
                category=Finding.Category.DEPENDENCY,
                summary=(
                    f"Parsed {len(packages)} package versions from lockfiles or "
                    "manifests, but SCANNER_OSV_ENABLED is off so CVE lookup was skipped."
                ),
                recommendation=(
                    "Set SCANNER_OSV_ENABLED=1 so The Lockfile can query the OSV "
                    "advisory database for known vulnerabilities."
                ),
                file_path=packages[0].file_path,
                rule_id="dependency.osv_disabled",
            )
        ]

    vulns_by_pkg = _query_osv(packages)
    findings: list[RawFinding] = []
    for pkg in packages:
        if not budget.can_emit():
            break
        key = (pkg.ecosystem, pkg.name.lower(), pkg.version)
        advisories = vulns_by_pkg.get(key) or []
        if not advisories:
            continue
        # One finding per package version (highest severity advisory summarized).
        top = max(advisories, key=lambda a: _severity_rank(a["severity"]))
        findings.append(
            RawFinding(
                title=f"Vulnerable dependency: {pkg.name}@{pkg.version}",
                severity=top["severity"],
                category=Finding.Category.DEPENDENCY,
                summary=(
                    f"{pkg.name} version {pkg.version} ({pkg.ecosystem}) is affected by "
                    f"{top['id']}: {top['summary']}. "
                    f"{len(advisories)} advisory(ies) matched this version."
                ),
                recommendation=(
                    f"Upgrade {pkg.name} to a fixed version. "
                    + (
                        f"Known fix versions include: {', '.join(top['fixed'])}. "
                        if top["fixed"]
                        else "Check the advisory for the earliest safe release. "
                    )
                    + f"Update the lockfile that pins it ({pkg.file_path}) and re-run tests. "
                    f"Advisory: https://osv.dev/vulnerability/{top['id']}"
                ),
                file_path=pkg.file_path,
                rule_id=f"dependency.osv.{pkg.ecosystem}.{pkg.name}.{pkg.version}",
            )
        )
        budget.record_emit()

    logger.info(
        "Dependencies scanner finished packages=%s findings=%s",
        len(packages),
        len(findings),
    )
    return findings


def _collect_packages(workspace: Path, *, budget) -> list[PackageRef]:
    found: list[PackageRef] = []
    seen: set[tuple[str, str, str]] = set()

    for path in workspace.rglob("*"):
        if budget.expired():
            break
        if not path.is_file() or path.name not in _MANIFEST_NAMES:
            continue
        # Skip nested vendor copies.
        parts = {p.lower() for p in path.parts}
        if parts & {"node_modules", "vendor", ".git", "dist", "build"}:
            continue
        relative = rel_path(workspace, path)
        text = read_text_file(path, max_bytes=2_000_000)
        if text is None:
            continue
        parsers = {
            "package-lock.json": _parse_package_lock,
            "yarn.lock": _parse_yarn_lock,
            "requirements.txt": _parse_requirements,
            "poetry.lock": _parse_poetry_lock,
            "Pipfile.lock": _parse_pipfile_lock,
            "go.mod": _parse_go_mod,
            "Cargo.lock": _parse_cargo_lock,
            "Gemfile.lock": _parse_gemfile_lock,
        }
        parser = parsers.get(path.name)
        if parser is None:
            continue
        for pkg in parser(text, relative):
            key = (pkg.ecosystem, pkg.name.lower(), pkg.version)
            if key in seen:
                continue
            seen.add(key)
            found.append(pkg)
    return found


def _parse_package_lock(text: str, file_path: str) -> list[PackageRef]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    out: list[PackageRef] = []
    packages = data.get("packages")
    if isinstance(packages, dict):
        for key, meta in packages.items():
            if not key or not isinstance(meta, dict):
                continue
            version = meta.get("version")
            if not version:
                continue
            name = meta.get("name") or key.rsplit("node_modules/", 1)[-1]
            if not name or name.startswith("node_modules"):
                continue
            out.append(
                PackageRef(
                    name=str(name),
                    version=str(version),
                    ecosystem="npm",
                    file_path=file_path,
                )
            )
        return out
    deps = data.get("dependencies")
    if isinstance(deps, dict):
        _walk_npm_deps(deps, out, file_path)
    return out


def _walk_npm_deps(deps: dict, out: list[PackageRef], file_path: str) -> None:
    for name, meta in deps.items():
        if not isinstance(meta, dict):
            continue
        version = meta.get("version")
        if version:
            out.append(
                PackageRef(
                    name=str(name),
                    version=str(version),
                    ecosystem="npm",
                    file_path=file_path,
                )
            )
        nested = meta.get("dependencies")
        if isinstance(nested, dict):
            _walk_npm_deps(nested, out, file_path)


def _parse_yarn_lock(text: str, file_path: str) -> list[PackageRef]:
    out: list[PackageRef] = []
    current_names: list[str] = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        if not line.startswith(" ") and line.rstrip().endswith(":"):
            header = line.strip().rstrip(":")
            # e.g. lodash@^4.17.0, lodash@~4.17.21:
            parts = [p.strip().strip('"') for p in header.split(",")]
            current_names = []
            for part in parts:
                name = part.rsplit("@", 1)[0] if "@" in part[1:] else part
                if name:
                    current_names.append(name)
            continue
        if current_names and line.strip().startswith("version "):
            version = line.split("version", 1)[1].strip().strip('"')
            for name in current_names:
                out.append(
                    PackageRef(
                        name=name,
                        version=version,
                        ecosystem="npm",
                        file_path=file_path,
                    )
                )
            current_names = []
    return out


def _parse_requirements(text: str, file_path: str) -> list[PackageRef]:
    out: list[PackageRef] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-"):
            continue
        match = _REQ_LINE.match(stripped)
        if not match:
            continue
        out.append(
            PackageRef(
                name=match.group(1),
                version=match.group(2),
                ecosystem="PyPI",
                file_path=file_path,
            )
        )
    return out


def _parse_poetry_lock(text: str, file_path: str) -> list[PackageRef]:
    out: list[PackageRef] = []
    name = None
    for line in text.splitlines():
        if line.strip() == "[[package]]":
            name = None
            continue
        if line.startswith("name = "):
            name = line.split("=", 1)[1].strip().strip('"')
        elif name and line.startswith("version = "):
            version = line.split("=", 1)[1].strip().strip('"')
            out.append(
                PackageRef(
                    name=name,
                    version=version,
                    ecosystem="PyPI",
                    file_path=file_path,
                )
            )
            name = None
    return out


def _parse_pipfile_lock(text: str, file_path: str) -> list[PackageRef]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    out: list[PackageRef] = []
    for section in ("default", "develop"):
        block = data.get(section) or {}
        if not isinstance(block, dict):
            continue
        for name, meta in block.items():
            if isinstance(meta, dict) and meta.get("version"):
                version = str(meta["version"]).lstrip("=")
                out.append(
                    PackageRef(
                        name=str(name),
                        version=version,
                        ecosystem="PyPI",
                        file_path=file_path,
                    )
                )
    return out


def _parse_go_mod(text: str, file_path: str) -> list[PackageRef]:
    out: list[PackageRef] = []
    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("require ("):
            in_block = True
            continue
        if in_block:
            if stripped == ")":
                in_block = False
                continue
            match = _GO_REQUIRE.match(stripped)
            if match:
                out.append(
                    PackageRef(
                        name=match.group(1),
                        version=f"v{match.group(2)}",
                        ecosystem="Go",
                        file_path=file_path,
                    )
                )
            continue
        if stripped.startswith("require ") and "(" not in stripped:
            match = _GO_REQUIRE.match(stripped[len("require ") :])
            if match:
                out.append(
                    PackageRef(
                        name=match.group(1),
                        version=f"v{match.group(2)}",
                        ecosystem="Go",
                        file_path=file_path,
                    )
                )
    return out


def _parse_cargo_lock(text: str, file_path: str) -> list[PackageRef]:
    out: list[PackageRef] = []
    name = None
    for line in text.splitlines():
        if line.strip() == "[[package]]":
            name = None
            continue
        m_name = _CARGO_NAME.match(line.strip())
        if m_name:
            name = m_name.group(1)
            continue
        m_ver = _CARGO_VERSION.match(line.strip())
        if name and m_ver:
            out.append(
                PackageRef(
                    name=name,
                    version=m_ver.group(1),
                    ecosystem="crates.io",
                    file_path=file_path,
                )
            )
            name = None
    return out


def _parse_gemfile_lock(text: str, file_path: str) -> list[PackageRef]:
    out: list[PackageRef] = []
    in_specs = False
    for line in text.splitlines():
        if line.startswith("  specs:"):
            in_specs = True
            continue
        if in_specs:
            if line and not line.startswith(" "):
                break
            if line.startswith("    ") and not line.startswith("      "):
                # e.g. "    rails (7.0.4)"
                stripped = line.strip()
                if "(" in stripped and stripped.endswith(")"):
                    name, _, rest = stripped.partition(" (")
                    version = rest[:-1]
                    if name and version:
                        out.append(
                            PackageRef(
                                name=name,
                                version=version,
                                ecosystem="RubyGems",
                                file_path=file_path,
                            )
                        )
    return out


def _query_osv(packages: list[PackageRef]) -> dict[tuple[str, str, str], list[dict]]:
    """
    Query OSV querybatch. On network failure, return empty and log.
    Result keyed by (ecosystem, name.lower(), version).
    """
    timeout = float(getattr(settings, "SCANNER_OSV_TIMEOUT_SECONDS", 30))
    # Batch in chunks to keep payloads reasonable.
    result: dict[tuple[str, str, str], list[dict]] = {}
    chunk_size = 80
    for start in range(0, len(packages), chunk_size):
        chunk = packages[start : start + chunk_size]
        payload = {
            "queries": [
                {
                    "package": {"name": p.name, "ecosystem": p.ecosystem},
                    "version": p.version,
                }
                for p in chunk
            ]
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            OSV_QUERYBATCH_URL,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
            logger.warning(
                "OSV advisory lookup failed or timed out; dependency CVEs skipped for chunk"
            )
            continue

        results = data.get("results") or []
        for pkg, entry in zip(chunk, results, strict=False):
            key = (pkg.ecosystem, pkg.name.lower(), pkg.version)
            vulns = entry.get("vulns") or []
            parsed: list[dict] = []
            for vuln in vulns:
                vuln_id = str(vuln.get("id") or "unknown")
                summary = str(vuln.get("summary") or vuln.get("details") or "Known vulnerability.")
                # Truncate long details.
                summary = summary.split("\n", 1)[0][:240]
                severity = _map_osv_severity(vuln)
                fixed = _extract_fixed_versions(vuln)
                parsed.append(
                    {
                        "id": vuln_id,
                        "summary": summary,
                        "severity": severity,
                        "fixed": fixed,
                    }
                )
            if parsed:
                result[key] = parsed
    return result


def _map_osv_severity(vuln: dict) -> str:
    database = (vuln.get("database_specific") or {}).get("severity")
    if isinstance(database, str):
        mapped = _normalize_severity_label(database)
        if mapped:
            return mapped
    for item in vuln.get("severity") or []:
        if not isinstance(item, dict):
            continue
        score = item.get("score")
        if isinstance(score, str) and score.upper().startswith("CVSS"):
            # Prefer explicit score number when present later.
            pass
        raw = item.get("type")
        if isinstance(item.get("score"), (int, float)):
            return _cvss_to_severity(float(item["score"]))
        if isinstance(score, str):
            # CVSS:3.1/AV:... sometimes; try numeric trailing
            try:
                # Some responses put vector in score; skip.
                if score.replace(".", "", 1).isdigit():
                    return _cvss_to_severity(float(score))
            except ValueError:
                pass
        if isinstance(raw, str):
            mapped = _normalize_severity_label(raw)
            if mapped:
                return mapped
    return Finding.Severity.MEDIUM


def _normalize_severity_label(label: str) -> str | None:
    value = label.strip().upper()
    mapping = {
        "CRITICAL": Finding.Severity.CRITICAL,
        "HIGH": Finding.Severity.HIGH,
        "MODERATE": Finding.Severity.MEDIUM,
        "MEDIUM": Finding.Severity.MEDIUM,
        "LOW": Finding.Severity.LOW,
    }
    return mapping.get(value)


def _cvss_to_severity(score: float) -> str:
    if score >= 9.0:
        return Finding.Severity.CRITICAL
    if score >= 7.0:
        return Finding.Severity.HIGH
    if score >= 4.0:
        return Finding.Severity.MEDIUM
    if score > 0:
        return Finding.Severity.LOW
    return Finding.Severity.INFO


def _extract_fixed_versions(vuln: dict) -> list[str]:
    fixed: list[str] = []
    for affected in vuln.get("affected") or []:
        if not isinstance(affected, dict):
            continue
        for rang in affected.get("ranges") or []:
            if not isinstance(rang, dict):
                continue
            for event in rang.get("events") or []:
                if isinstance(event, dict) and event.get("fixed"):
                    fixed.append(str(event["fixed"]))
    # Dedup preserve order
    seen: set[str] = set()
    out: list[str] = []
    for item in fixed:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out[:5]


def _severity_rank(severity: str) -> int:
    order = {
        Finding.Severity.CRITICAL: 5,
        Finding.Severity.HIGH: 4,
        Finding.Severity.MEDIUM: 3,
        Finding.Severity.LOW: 2,
        Finding.Severity.INFO: 1,
    }
    return order.get(severity, 0)
