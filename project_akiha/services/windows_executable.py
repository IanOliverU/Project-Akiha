"""Helpers for inspecting Windows executable metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

WINDOWS_GUI_SUBSYSTEM = 2
WINDOWS_CONSOLE_SUBSYSTEM = 3

_DOS_PE_POINTER_OFFSET = 0x3C
_COFF_HEADER_SIZE = 20
_OPTIONAL_HEADER_SIZE_OFFSET = 16
_SUBSYSTEM_OFFSET = 0x44


@dataclass(frozen=True, slots=True)
class WindowsExecutableInfo:
    """Small subset of PE metadata needed by the packaging smoke checks."""

    subsystem: int

    @property
    def subsystem_name(self) -> str:
        """Return a readable name for the PE subsystem value."""
        if self.subsystem == WINDOWS_GUI_SUBSYSTEM:
            return "Windows GUI"
        if self.subsystem == WINDOWS_CONSOLE_SUBSYSTEM:
            return "Windows console"

        return f"Unknown ({self.subsystem})"

    @property
    def is_windows_gui(self) -> bool:
        """Return whether this executable uses the Windows GUI subsystem."""
        return self.subsystem == WINDOWS_GUI_SUBSYSTEM


class WindowsExecutableError(ValueError):
    """Raised when a file is not a readable Windows PE executable."""


def read_windows_executable_info(executable_path: Path) -> WindowsExecutableInfo:
    """Read Windows PE subsystem metadata from an executable."""
    data = executable_path.read_bytes()
    if len(data) < _DOS_PE_POINTER_OFFSET + 4:
        raise WindowsExecutableError(f"File is too small: {executable_path}")

    pe_offset = int.from_bytes(
        data[_DOS_PE_POINTER_OFFSET : _DOS_PE_POINTER_OFFSET + 4],
        byteorder="little",
    )
    if pe_offset <= 0 or pe_offset + 4 + _COFF_HEADER_SIZE > len(data):
        raise WindowsExecutableError(f"Invalid PE header offset: {executable_path}")

    if data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise WindowsExecutableError(f"Missing PE signature: {executable_path}")

    coff_header_offset = pe_offset + 4
    optional_header_size_offset = coff_header_offset + _OPTIONAL_HEADER_SIZE_OFFSET
    optional_header_size = int.from_bytes(
        data[optional_header_size_offset : optional_header_size_offset + 2],
        byteorder="little",
    )
    if optional_header_size < _SUBSYSTEM_OFFSET + 2:
        raise WindowsExecutableError(
            f"Optional PE header is too small: {executable_path}"
        )

    optional_header_offset = coff_header_offset + _COFF_HEADER_SIZE
    subsystem_offset = optional_header_offset + _SUBSYSTEM_OFFSET
    if subsystem_offset + 2 > len(data):
        raise WindowsExecutableError(f"Missing PE subsystem field: {executable_path}")

    subsystem = int.from_bytes(
        data[subsystem_offset : subsystem_offset + 2],
        byteorder="little",
    )
    return WindowsExecutableInfo(subsystem=subsystem)
