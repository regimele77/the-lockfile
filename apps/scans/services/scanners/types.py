"""Shared types for scanner results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RawFinding:
    """One candidate finding before persistence."""

    title: str
    severity: str
    category: str
    summary: str
    recommendation: str
    file_path: str = ""
    rule_id: str = ""
