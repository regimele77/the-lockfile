"""Resolved host technical knobs (DB singleton, seeded from env settings)."""

from __future__ import annotations

from apps.core.models import TechnicalConfiguration


def get_technical_configuration() -> TechnicalConfiguration:
    return TechnicalConfiguration.load()


def clone_timeout_seconds() -> int:
    return max(30, int(get_technical_configuration().clone_timeout_seconds))


def clone_depth() -> int:
    return max(1, int(get_technical_configuration().clone_depth))


def max_repo_size_mb() -> int:
    return max(1, int(get_technical_configuration().max_repo_size_mb))


def reschedule_hours() -> int:
    return max(1, int(get_technical_configuration().reschedule_hours))


def schedule_check_hours() -> int:
    return max(1, int(get_technical_configuration().schedule_check_hours))


def scanner_timeout_seconds() -> float:
    return float(max(5, int(get_technical_configuration().scanner_timeout_seconds)))


def max_findings_per_scanner() -> int:
    return max(1, int(get_technical_configuration().max_findings_per_scanner))


def max_file_bytes() -> int:
    return max(1, int(get_technical_configuration().max_file_bytes))


def max_files() -> int:
    return max(1, int(get_technical_configuration().max_files))


def osv_timeout_seconds() -> float:
    return float(max(1, int(get_technical_configuration().osv_timeout_seconds)))


def osv_max_packages() -> int:
    return max(1, int(get_technical_configuration().osv_max_packages))


def github_timeout_seconds() -> float:
    return float(max(1, int(get_technical_configuration().github_timeout_seconds)))
