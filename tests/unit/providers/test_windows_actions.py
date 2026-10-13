"""Platform adapters preserve launch arguments and normal window-close scope."""

import ast
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from project_akiha.providers import windows_actions


class WindowsActionsTest(unittest.TestCase):
    def test_openers_pass_exact_path_to_default_handler(self):
        path = Path("C:/approved/path with spaces")
        with patch.object(windows_actions.os, "startfile", create=True) as start:
            windows_actions.open_directory(path)
            windows_actions.open_file(path)
        self.assertEqual(start.call_args_list[0].args, (str(path),))
        self.assertEqual(start.call_args_list[1].args, (str(path),))

    def test_launcher_uses_one_executable_without_shell_or_arguments(self):
        path = Path("C:/approved/app.exe")
        with patch.object(windows_actions.subprocess, "Popen") as launch:
            windows_actions.launch_application(path)
        launch.assert_called_once_with(
            [str(path)],
            shell=False,
            stdin=windows_actions.subprocess.DEVNULL,
            stdout=windows_actions.subprocess.DEVNULL,
            stderr=windows_actions.subprocess.DEVNULL,
            close_fds=True,
        )

    def test_composition_injects_correct_adapter_for_each_executor(self):
        source = Path(__file__).resolve().parents[3] / "project_akiha/app/main.py"
        expected = {
            "OpenDirectoryExecutor": "open_directory",
            "OpenFileExecutor": "open_file",
            "AllowlistedApplicationExecutor": "launch_application",
            "CloseAllowlistedApplicationExecutor": "close_application_windows",
        }
        calls = [
            node
            for node in ast.walk(ast.parse(source.read_text(encoding="utf-8-sig")))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in expected
        ]
        self.assertEqual(len(calls), 4)
        for call in calls:
            adapter = call.args[-1]
            self.assertIsInstance(adapter, ast.Attribute)
            self.assertEqual(adapter.value.id, "windows_actions")
            self.assertEqual(adapter.attr, expected[call.func.id])

    def test_close_posts_only_to_exact_executable_and_closes_handles(self):
        import ctypes

        kernel = Mock()
        user = Mock()
        kernel.OpenProcess.return_value = 99
        user.GetWindowThreadProcessId.side_effect = lambda _window, pid: setattr(
            pid._obj, "value", 10
        )
        executables = iter(["C:/approved/app.exe", "C:/other/app.exe"])

        def query(_process, _flags, buffer, _capacity):
            buffer.value = next(executables)
            return True

        kernel.QueryFullProcessImageNameW.side_effect = query

        def enumerate_windows(callback, _parameter):
            self.assertTrue(callback(1, 0))
            self.assertTrue(callback(2, 0))
            return True

        user.EnumWindows.side_effect = enumerate_windows
        with patch.object(ctypes, "WinDLL", side_effect=[kernel, user]):
            result = windows_actions.close_application_windows(
                Path("C:/approved/app.exe")
            )
        self.assertEqual(result, 1)
        user.PostMessageW.assert_called_once_with(1, 0x0010, 0, 0)
        self.assertEqual(kernel.CloseHandle.call_count, 2)
