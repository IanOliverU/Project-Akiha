"""Opt-in lifecycle evidence in a fresh isolated application-data directory."""

from __future__ import annotations

import json
from pathlib import Path


def shutdown_smoke_request(arguments: list[str], data_dir: Path) -> Path | None:
    prefix = "--utility-shutdown-smoke-report="
    values = [arg[len(prefix) :] for arg in arguments if arg.startswith(prefix)]
    if not values:
        return None
    if len(values) != 1:
        raise ValueError("One isolated shutdown report is required.")
    report = Path(values[0])
    if (
        not report.is_absolute()
        or report.suffix != ".json"
        or not report.parent.is_dir()
        or report.exists()
        or data_dir.resolve() != (report.parent / "data" / "Akiha").resolve()
        or data_dir.exists()
    ):
        raise ValueError("Shutdown smoke requires fresh isolated application data.")
    return report


def write_shutdown_smoke_report(report: Path, checks: dict[str, bool]) -> None:
    """Publish only closed boolean checks; never application content or paths."""
    if not checks or any(type(value) is not bool for value in checks.values()):
        raise ValueError("Invalid lifecycle checks.")
    with report.open("x", encoding="utf-8") as stream:
        json.dump({"passed": all(checks.values()), "checks": checks}, stream, indent=2)


def shutdown_smoke_passed(report: Path) -> bool:
    try:
        value = json.loads(report.read_text(encoding="utf-8"))
        return value.get("passed") is True and bool(value.get("checks"))
    except (OSError, ValueError, AttributeError):
        return False
