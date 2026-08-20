"""Tests for observable Google Gen AI SDK loading."""

from __future__ import annotations

import builtins
import unittest
from unittest.mock import patch

from project_akiha.providers.live.google_sdk import probe_google_genai_sdk


class GoogleGenAISdkTest(unittest.TestCase):
    def test_real_source_sdk_import_is_complete(self) -> None:
        probe = probe_google_genai_sdk()

        self.assertTrue(probe.available, probe.detail)
        self.assertFalse(probe.missing_module)

    def test_missing_transitive_module_is_named_without_raw_exception(self) -> None:
        real_import = builtins.__import__

        def fail_google_import(name, *args, **kwargs):
            if name == "google":
                error = ModuleNotFoundError("private local path")
                error.name = "google.auth.transport"
                raise error
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fail_google_import):
            probe = probe_google_genai_sdk()

        self.assertFalse(probe.available)
        self.assertEqual(probe.missing_module, "google.auth.transport")
        self.assertIn("google.auth.transport", probe.detail)
        self.assertNotIn("private local path", probe.detail)


if __name__ == "__main__":
    unittest.main()
