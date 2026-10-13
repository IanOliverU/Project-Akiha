"""Isolated lifecycle diagnostics cannot touch an existing owner profile."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.services.utility_shutdown_smoke import (
    shutdown_smoke_passed,
    shutdown_smoke_request,
    write_shutdown_smoke_report,
)


class UtilityShutdownSmokeTest(unittest.TestCase):
    def test_opt_in_requires_fresh_isolated_profile_and_new_report(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            report = root / "shutdown.json"
            data = root / "data" / "Akiha"
            args = [f"--utility-shutdown-smoke-report={report}"]
            self.assertIsNone(shutdown_smoke_request([], data))
            self.assertEqual(shutdown_smoke_request(args, data), report)
            with self.assertRaises(ValueError):
                shutdown_smoke_request(args, root / "owner")
            data.mkdir(parents=True)
            with self.assertRaises(ValueError):
                shutdown_smoke_request(args, data)

    def test_boolean_only_report_fail_closed_and_no_overwrite(self):
        with TemporaryDirectory() as folder:
            report = Path(folder) / "shutdown.json"
            self.assertFalse(shutdown_smoke_passed(report))
            with self.assertRaises(ValueError):
                write_shutdown_smoke_report(report, {"private": "secret"})
            write_shutdown_smoke_report(report, {"pending": True, "joined": False})
            self.assertFalse(shutdown_smoke_passed(report))
            self.assertEqual(json.loads(report.read_text())["checks"]["pending"], True)
            with self.assertRaises(FileExistsError):
                write_shutdown_smoke_report(report, {"pending": True})
