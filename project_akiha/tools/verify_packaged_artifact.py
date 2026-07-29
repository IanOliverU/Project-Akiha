"""Verify that a Nuitka standalone artifact contains required runtime files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from project_akiha.services.package_artifact import validate_package_artifact


def main(argv: list[str] | None = None) -> int:
    """Run the packaged artifact verification command."""
    parser = argparse.ArgumentParser(
        description="Verify Project Akiha standalone package contents."
    )
    parser.add_argument("artifact_dir", type=Path)
    args = parser.parse_args(argv)

    if not args.artifact_dir.exists():
        print(f"Packaged artifact directory is missing: {args.artifact_dir}")
        return 1

    issues = validate_package_artifact(args.artifact_dir)
    if issues:
        print("Packaged artifact validation failed:", file=sys.stderr)
        for issue in issues:
            print(f"{issue.path}: {issue.message}", file=sys.stderr)
        return 1

    print(f"Packaged artifact OK: {args.artifact_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
