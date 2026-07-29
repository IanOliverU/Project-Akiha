"""Smoke-test log inspection helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_FAILURE_MARKERS = (
    " ERROR ",
    " CRITICAL ",
    "Traceback (most recent call last):",
)


@dataclass(frozen=True, slots=True)
class SmokeLogIssue:
    """One unexpected smoke-test log issue."""

    line_number: int
    content: str


def find_smoke_log_issues(log_path: Path) -> tuple[SmokeLogIssue, ...]:
    """Return unexpected error/traceback lines from an app smoke log."""
    issues: list[SmokeLogIssue] = []
    for line_number, line in enumerate(
        log_path.read_text(encoding="utf-8", errors="replace").splitlines(),
        start=1,
    ):
        if any(marker in line for marker in _FAILURE_MARKERS):
            issues.append(SmokeLogIssue(line_number=line_number, content=line))

    return tuple(issues)
