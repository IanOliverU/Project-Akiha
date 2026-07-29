"""Minimal Nuitka diagnostic entry point."""

from __future__ import annotations


def main() -> int:
    """Print a marker for frozen-runtime checks."""
    print("minimal diagnostic ok", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
