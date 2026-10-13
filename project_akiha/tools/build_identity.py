"""Fail on release dependency drift and bind dirty source to artifact bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

LOCK = Path("requirements/release-win-py313.txt")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inventory() -> dict[str, str]:
    return dict(
        sorted(
            (canonicalize_name(dist.metadata["Name"]), dist.version)
            for dist in metadata.distributions()
        )
    )


def check_lock(lock: Path = LOCK, installed: dict[str, str] | None = None) -> None:
    installed = inventory() if installed is None else installed
    errors = []
    locked_names = set()
    for line in lock.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        requirement = Requirement(line)
        pins = list(requirement.specifier)
        if len(pins) != 1 or pins[0].operator != "==" or "*" in pins[0].version:
            raise ValueError("Release requirements must use exact pins")
        name = canonicalize_name(requirement.name)
        locked_names.add(name)
        if installed.get(name) != pins[0].version:
            errors.append(
                f"{name}: expected {pins[0].version}, "
                f"found {installed.get(name, 'missing')}"
            )
    unexpected = set(installed) - locked_names - {"project-akiha"}
    if unexpected:
        errors.append("Unpinned distributions: " + ", ".join(sorted(unexpected)))
    if errors:
        raise RuntimeError("Release dependency drift:\n" + "\n".join(errors))


def file_manifest(root: Path, paths: list[Path]) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): digest(path.read_bytes())
        for path in sorted(paths)
        if path.is_file()
    }


def git(*args: str) -> bytes:
    # The verification host may run this authorized checkout under a different
    # Windows token. Scope the ownership exception to this invocation only.
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={Path.cwd().as_posix()}", *args]
    )


def source_identity() -> dict:
    root = Path.cwd().resolve()
    names = set(
        git("ls-files", "-c", "-o", "--exclude-standard", "-z")
        .decode("utf-8")
        .split("\0")
    ) - {""}
    files = file_manifest(root, [root / name for name in names])
    return {
        "head": git("rev-parse", "HEAD").decode().strip(),
        "head_tree": git("rev-parse", "HEAD^{tree}").decode().strip(),
        "status": git("status", "--porcelain=v1").decode(),
        "working_tree_sha256": digest(json.dumps(files, sort_keys=True).encode()),
        "files": files,
    }


def capture_inputs() -> dict:
    check_lock()
    return {
        "schema_version": 1,
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "dependencies": inventory(),
        "release_lock_sha256": digest(LOCK.read_bytes()),
        "source": source_identity(),
    }


def finalize(inputs: dict, artifact: Path) -> dict:
    current = capture_inputs()
    if current != inputs:
        raise RuntimeError(
            "Build inputs changed while building; candidate is not attributable"
        )
    artifact = artifact.resolve()
    files = file_manifest(artifact, list(artifact.rglob("*")))
    if not files:
        raise ValueError("Artifact is empty")
    return {
        **inputs,
        "artifact": {
            "directory": str(artifact),
            "files": files,
            "tree_sha256": digest(json.dumps(files, sort_keys=True).encode()),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("check", "capture", "finalize"))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--artifact", type=Path)
    args = parser.parse_args()
    if args.operation == "check":
        check_lock()
    else:
        if args.report is None:
            parser.error("--report is required")
        if args.operation == "capture":
            result = capture_inputs()
        else:
            if args.inputs is None or args.artifact is None:
                parser.error("finalize requires --inputs and --artifact")
            result = finalize(
                json.loads(args.inputs.read_text(encoding="utf-8")), args.artifact
            )
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Release identity {args.operation}: PASS")


if __name__ == "__main__":
    main()
