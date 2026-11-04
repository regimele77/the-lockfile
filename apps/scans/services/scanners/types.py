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
    line_number: int | None = None
    # When None, persist decides via git (path present in HEAD).
    github_linkable: bool | None = None
