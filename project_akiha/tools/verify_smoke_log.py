"""Verify that a smoke-test app log has no unexpected failures."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from project_akiha.services.smoke_log import find_smoke_log_issues


def main(argv: list[str] | None = None) -> int:
    """Run the smoke log verification command."""
    parser = argparse.ArgumentParser(
        description="Verify that an Akiha smoke-test app log has no failures."
    )
    parser.add_argument("log_path", type=Path)
    args = parser.parse_args(argv)

    if not args.log_path.exists():
        print(f"Smoke log was not created: {args.log_path}", file=sys.stderr)
        return 1

    issues = find_smoke_log_issues(args.log_path)
    if issues:
        print("Smoke log contains unexpected failure lines:", file=sys.stderr)
        for issue in issues:
            print(f"{issue.line_number}: {issue.content}", file=sys.stderr)
        return 1

    print(f"Smoke log OK: {args.log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
