"""Tests for top-level startup failure logging."""

from __future__ import annotations

import logging
import os
import unittest
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tempfile import TemporaryDirectory

import project_akiha.app.main as main_module


class StartupFailureLoggingTest(unittest.TestCase):
    """Verify unrecoverable startup failures are written to app logs."""

    def test_main_logs_startup_failure_before_reraising(self) -> None:
        original_run_application = main_module._run_application
        original_local_app_data = os.environ.get("LOCALAPPDATA")

        def fail_startup() -> int:
            raise RuntimeError("startup boom")

        with TemporaryDirectory() as directory:
            os.environ["LOCALAPPDATA"] = directory
            main_module._run_application = fail_startup
            try:
                with self.assertRaisesRegex(RuntimeError, "startup boom"):
                    main_module.main()
            finally:
                main_module._run_application = original_run_application
                if original_local_app_data is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = original_local_app_data

            log_path = Path(directory) / "Akiha" / "logs" / "app.log"
            log_text = log_path.read_text(encoding="utf-8")
            _close_handlers_under(Path(directory))

        self.assertIn("Project Akiha failed during startup.", log_text)
        self.assertIn("startup boom", log_text)


def _close_handlers_under(directory: Path) -> None:
    logger = logging.getLogger("project_akiha")
    for handler in tuple(logger.handlers):
        if isinstance(handler, RotatingFileHandler) and Path(
            handler.baseFilename
        ).is_relative_to(directory):
            logger.removeHandler(handler)
            handler.close()


if __name__ == "__main__":
    unittest.main()
