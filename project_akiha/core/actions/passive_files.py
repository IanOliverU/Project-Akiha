"""Default-deny policy for opening passive user files."""

from __future__ import annotations

import stat
from collections.abc import Iterable
from pathlib import Path

from project_akiha.core.actions.errors import ActionValidationError
from project_akiha.core.actions.models import ActionFailureCategory

_WINDOWS_REPARSE_POINT = 0x400

PASSIVE_TEXT_EXTENSIONS = frozenset(
    {".txt", ".md", ".csv", ".json", ".log", ".yaml", ".yml", ".toml", ".ini"}
)
PASSIVE_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"})
PASSIVE_AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".flac", ".ogg", ".m4a"})
PASSIVE_VIDEO_EXTENSIONS = frozenset({".mp4", ".mkv", ".webm", ".avi", ".mov"})
PASSIVE_DOCUMENT_EXTENSIONS = frozenset({".pdf"})
PASSIVE_FILE_EXTENSIONS = frozenset(
    {
        *PASSIVE_TEXT_EXTENSIONS,
        *PASSIVE_IMAGE_EXTENSIONS,
        *PASSIVE_AUDIO_EXTENSIONS,
        *PASSIVE_VIDEO_EXTENSIONS,
        *PASSIVE_DOCUMENT_EXTENSIONS,
    }
)

# Kept as an explicit reference for diagnostics and tests. Enforcement remains
# default-deny through PASSIVE_FILE_EXTENSIONS, so new active formats cannot
# become openable merely by being omitted from this list.
BLOCKED_ACTIVE_EXTENSIONS = frozenset(
    {
        ".exe",
        ".com",
        ".scr",
        ".bat",
        ".cmd",
        ".ps1",
        ".vbs",
        ".js",
        ".msi",
        ".msix",
        ".reg",
        ".cpl",
        ".lnk",
        ".url",
    }
)


class PassiveFilePolicy:
    """Validate existing regular files against a narrow extension allowlist."""

    def __init__(
        self,
        allowed_extensions: Iterable[str] = PASSIVE_FILE_EXTENSIONS,
    ) -> None:
        normalized = frozenset(
            extension.strip().casefold() for extension in allowed_extensions
        )
        if not normalized or any(
            not extension.startswith(".") or len(extension) == 1
            for extension in normalized
        ):
            raise ValueError("passive file extensions must be non-empty suffixes.")
        self._allowed_extensions = normalized

    @property
    def allowed_extensions(self) -> frozenset[str]:
        """Return the normalized extensions accepted by this policy."""
        return self._allowed_extensions

    def validate_file(self, path: Path) -> Path:
        """Return an existing regular file or raise a sanitized rejection."""
        try:
            details = path.lstat()
        except OSError as error:
            raise ActionValidationError(
                ActionFailureCategory.TARGET_UNAVAILABLE,
                "The requested file is unavailable.",
            ) from error

        attributes = getattr(details, "st_file_attributes", 0)
        if (
            stat.S_ISLNK(details.st_mode)
            or attributes & _WINDOWS_REPARSE_POINT
            or not stat.S_ISREG(details.st_mode)
        ):
            raise ActionValidationError(
                ActionFailureCategory.INVALID_TARGET,
                "Only regular passive files can be opened.",
            )

        if path.suffix.casefold() not in self._allowed_extensions:
            raise ActionValidationError(
                ActionFailureCategory.INVALID_TARGET,
                "The file type is not allowlisted for passive opening.",
            )
        return path

    def is_allowed(self, path: Path) -> bool:
        """Return whether a path currently satisfies this policy."""
        try:
            self.validate_file(path)
        except ActionValidationError:
            return False
        return True
