"""Conservative Windows path policy for scoped assistant permissions."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterable, Mapping
from pathlib import Path

from project_akiha.core.actions.errors import ActionValidationError
from project_akiha.core.actions.models import ActionFailureCategory

_WINDOWS_REPARSE_POINT = 0x400


class ProtectedPathPolicy:
    """Canonicalize local paths and reject protected or ambiguous targets."""

    def __init__(
        self,
        protected_roots: Iterable[Path] = (),
        credential_path: Path | None = None,
    ) -> None:
        self._protected_roots = tuple(
            _resolve_without_strict(path) for path in protected_roots
        )
        self._credential_path = (
            _resolve_without_strict(credential_path)
            if credential_path is not None
            else None
        )

    @classmethod
    def for_current_windows(
        cls,
        *,
        credential_path: Path,
        environ: Mapping[str, str] | None = None,
    ) -> ProtectedPathPolicy:
        """Build the default protected-root policy from Windows environment data."""
        env = environ if environ is not None else os.environ
        protected: list[Path] = []
        for name in (
            "SystemRoot",
            "WINDIR",
            "ProgramFiles",
            "ProgramFiles(x86)",
            "ProgramW6432",
            "ProgramData",
        ):
            value = env.get(name)
            if value:
                protected.append(Path(value))

        system_drive = env.get("SystemDrive")
        if system_drive:
            drive = Path(f"{system_drive}\\")
            protected.extend(
                (
                    drive / "$Recycle.Bin",
                    drive / "Boot",
                    drive / "Recovery",
                    drive / "System Volume Information",
                )
            )

        return cls(protected_roots=protected, credential_path=credential_path)

    def validate_path(self, value: str) -> Path:
        """Return a canonical local path or reject it as unsafe."""
        normalized = value.strip()
        if not normalized:
            raise _invalid_target("The action path cannot be empty.")
        if "\x00" in normalized:
            raise _invalid_target("The action path contains an invalid character.")
        if _is_network_or_device_path(normalized):
            raise _invalid_target("Network and device paths are not allowed.")

        path = Path(normalized).expanduser()
        if not path.is_absolute():
            raise _invalid_target("Assistant action paths must be absolute.")
        if _has_alternate_data_stream(path):
            raise _invalid_target("Alternate data streams are not allowed.")
        if _contains_existing_reparse_point(path):
            raise _invalid_target("Paths through links or reparse points are blocked.")

        canonical = _resolve_without_strict(path)
        if _is_drive_root(canonical):
            raise _invalid_target("Drive roots cannot be approved.")
        if self._is_protected(canonical):
            raise _invalid_target("The requested path is protected.")
        return canonical

    def is_within(self, target: str | Path, approved_root: str | Path) -> bool:
        """Return whether a validated target remains inside an approved root."""
        try:
            canonical_target = self.validate_path(str(target))
            canonical_root = self.validate_path(str(approved_root))
        except ActionValidationError:
            return False
        return (
            canonical_target == canonical_root
            or canonical_root in canonical_target.parents
        )

    def _is_protected(self, path: Path) -> bool:
        if self._credential_path is not None and path == self._credential_path:
            return True
        return any(
            path == root or root in path.parents for root in self._protected_roots
        )


def _resolve_without_strict(path: Path) -> Path:
    return path.resolve(strict=False)


def _is_network_or_device_path(value: str) -> bool:
    normalized = value.replace("/", "\\")
    return normalized.startswith(("\\\\", "\\\\?\\", "\\\\.\\"))


def _has_alternate_data_stream(path: Path) -> bool:
    text = str(path)
    drive = path.drive
    remainder = text[len(drive) :] if drive else text
    return ":" in remainder


def _is_drive_root(path: Path) -> bool:
    return bool(path.anchor) and path == Path(path.anchor)


def _contains_existing_reparse_point(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            details = current.lstat()
        except OSError:
            continue
        attributes = getattr(details, "st_file_attributes", 0)
        if stat.S_ISLNK(details.st_mode) or attributes & _WINDOWS_REPARSE_POINT:
            return True
    return False


def _invalid_target(message: str) -> ActionValidationError:
    return ActionValidationError(ActionFailureCategory.INVALID_TARGET, message)
