"""Keep architecture enforcement in normal full test discovery."""

import unittest
from pathlib import Path

from project_akiha.tools.verify_core_boundaries import check_core, violations


class CoreImportBoundaryTest(unittest.TestCase):
    def test_repository_core_has_no_concrete_platform_or_outer_imports(self):
        check_core(Path(__file__).resolve().parents[3] / "project_akiha/core")

    def test_alias_nested_and_execution_lookup_violations_are_rejected(self):
        for source in (
            "import ctypes as native",
            "from subprocess import Popen as launch",
            "from os import startfile as open_path",
            "import os as platform; platform.startfile('x')",
            "import os; getattr(os, 'startfile', None)",
            "def f():\n from project_akiha.providers import x",
            "__import__('ctypes')",
            "import win32api",
            "import PySide6.QtCore",
            "from ...providers import windows_actions",
            "from project_akiha import services",
            "from ... import integrations",
            "import importlib as loader",
            "from os import execve as launch",
        ):
            with self.subTest(source=source):
                self.assertTrue(violations(source))
        self.assertEqual(
            violations("import os\nfrom pathlib import Path\nos.scandir(Path('.'))"), []
        )
