"""Release receipts reject dependency/source drift and cover artifact bytes."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from project_akiha.tools.build_identity import check_lock, digest, finalize, git


class BuildIdentityTest(unittest.TestCase):
    def test_git_ownership_exception_is_invocation_local(self):
        with patch(
            "project_akiha.tools.build_identity.subprocess.check_output",
            return_value=b"revision",
        ) as run:
            self.assertEqual(git("rev-parse", "HEAD"), b"revision")
        run.assert_called_once_with(
            [
                "git",
                "-c",
                f"safe.directory={Path.cwd().as_posix()}",
                "rev-parse",
                "HEAD",
            ]
        )

    def test_lock_rejects_missing_wrong_or_ranged_dependency(self):
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp) / "requirements.txt"
            lock.write_text("example==1.2\n")
            check_lock(lock, {"example": "1.2"})
            for inventory in ({}, {"example": "1.3"}, {"example": "1.2", "extra": "1"}):
                with self.assertRaises(RuntimeError):
                    check_lock(lock, inventory)
            lock.write_text("example>=1.2\n")
            with self.assertRaises(ValueError):
                check_lock(lock, {"example": "1.2"})

    def test_source_drift_fails_and_artifact_receipt_covers_nested_files(self):
        inputs = {"source": {"working_tree_sha256": "original"}}
        with tempfile.TemporaryDirectory() as temp:
            artifact = Path(temp)
            (artifact / "nested").mkdir()
            (artifact / "nested/library.dll").write_bytes(b"library")
            (artifact / "Akiha.exe").write_bytes(b"executable")
            with patch(
                "project_akiha.tools.build_identity.capture_inputs", return_value=inputs
            ):
                receipt = finalize(inputs, artifact)
            self.assertEqual(
                receipt["artifact"]["files"],
                {
                    "Akiha.exe": digest(b"executable"),
                    "nested/library.dll": digest(b"library"),
                },
            )
            with patch(
                "project_akiha.tools.build_identity.capture_inputs",
                return_value={"source": "changed"},
            ):
                with self.assertRaises(RuntimeError):
                    finalize(inputs, artifact)
