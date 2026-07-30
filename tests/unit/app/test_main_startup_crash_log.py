"""Tests for frozen GUI startup traceback capture."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from project_akiha.app.main import _write_startup_crash_log


class MainStartupCrashLogTest(unittest.TestCase):
    """Verify suppressed GUI-subsystem tracebacks remain diagnosable."""

    def test_writes_active_exception_to_local_log_directory(self) -> None:
        with TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"LOCALAPPDATA": directory}):
                try:
                    raise RuntimeError("startup failed")
                except RuntimeError:
                    _write_startup_crash_log()

            crash_log = Path(directory) / "Akiha" / "logs" / "startup-crash.log"
            content = crash_log.read_text(encoding="utf-8")

        self.assertIn("RuntimeError: startup failed", content)
