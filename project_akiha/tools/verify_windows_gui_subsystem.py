"""Verify that a Windows executable is built for the GUI subsystem."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from project_akiha.services.windows_executable import (
    WindowsExecutableError,
    read_windows_executable_info,
)


def main(argv: list[str] | None = None) -> int:
    """Run the Windows GUI subsystem verification command."""
    parser = argparse.ArgumentParser(
        description="Verify that a Windows executable does not use a console subsystem."
    )
    parser.add_argument("exe_path", type=Path)
    args = parser.parse_args(argv)

    try:
        info = read_windows_executable_info(args.exe_path)
    except (OSError, WindowsExecutableError) as error:
        print(f"Executable subsystem check failed: {error}", file=sys.stderr)
        return 1

    print(f"Executable subsystem: {info.subsystem_name}")
    if not info.is_windows_gui:
        print(
            "Expected a Windows GUI subsystem executable.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
