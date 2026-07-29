"""Tests for Windows executable metadata parsing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from project_akiha.services.windows_executable import (
    WINDOWS_CONSOLE_SUBSYSTEM,
    WINDOWS_GUI_SUBSYSTEM,
    WindowsExecutableError,
    read_windows_executable_info,
)


class WindowsExecutableInfoTest(unittest.TestCase):
    """Verify PE subsystem parsing."""

    def test_reads_windows_gui_subsystem(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            exe_path = Path(directory) / "gui.exe"
            exe_path.write_bytes(_minimal_pe(subsystem=WINDOWS_GUI_SUBSYSTEM))

            info = read_windows_executable_info(exe_path)

        self.assertTrue(info.is_windows_gui)
        self.assertEqual(info.subsystem_name, "Windows GUI")

    def test_reads_windows_console_subsystem(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            exe_path = Path(directory) / "console.exe"
            exe_path.write_bytes(_minimal_pe(subsystem=WINDOWS_CONSOLE_SUBSYSTEM))

            info = read_windows_executable_info(exe_path)

        self.assertFalse(info.is_windows_gui)
        self.assertEqual(info.subsystem_name, "Windows console")

    def test_rejects_non_pe_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            exe_path = Path(directory) / "not.exe"
            exe_path.write_text("not an executable", encoding="utf-8")

            with self.assertRaises(WindowsExecutableError):
                read_windows_executable_info(exe_path)


def _minimal_pe(*, subsystem: int) -> bytes:
    pe_offset = 0x80
    optional_header_size = 0x70
    data = bytearray(pe_offset + 4 + 20 + optional_header_size)
    data[0:2] = b"MZ"
    data[0x3C:0x40] = pe_offset.to_bytes(4, byteorder="little")
    data[pe_offset : pe_offset + 4] = b"PE\0\0"

    coff_header_offset = pe_offset + 4
    optional_header_size_offset = coff_header_offset + 16
    data[optional_header_size_offset : optional_header_size_offset + 2] = (
        optional_header_size.to_bytes(2, byteorder="little")
    )

    optional_header_offset = coff_header_offset + 20
    data[optional_header_offset : optional_header_offset + 2] = (0x20B).to_bytes(
        2,
        byteorder="little",
    )
    subsystem_offset = optional_header_offset + 0x44
    data[subsystem_offset : subsystem_offset + 2] = subsystem.to_bytes(
        2,
        byteorder="little",
    )
    return bytes(data)
