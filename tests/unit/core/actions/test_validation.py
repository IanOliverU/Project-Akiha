"""Tests for action schema and target validation."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.core.actions import (
    ActionFailureCategory,
    ActionRequest,
    ActionRequestValidator,
    ActionValidationError,
    ProtectedPathPolicy,
    build_default_action_registry,
)


class ActionRequestValidatorTest(unittest.TestCase):
    """Verify untrusted request fields are normalized and constrained."""

    def setUp(self) -> None:
        self._temporary_directory = TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.root = Path(self._temporary_directory.name)
        self.safe_root = self.root / "Documents"
        self.safe_root.mkdir()
        self.protected_root = self.root / "Windows"
        self.protected_root.mkdir()
        self.validator = ActionRequestValidator(
            build_default_action_registry(),
            ProtectedPathPolicy(protected_roots=(self.protected_root,)),
        )

    def test_validates_and_normalizes_file_search(self) -> None:
        request = self._request(
            "files.search",
            {
                "root": f"  {self.safe_root}  ",
                "query": " report ",
                "media_only": True,
            },
        )

        result = self.validator.validate(request)

        self.assertEqual(result.normalized_target, str(self.safe_root.resolve()))
        self.assertEqual(result.parameters["query"], "report")
        self.assertTrue(result.parameters["media_only"])

    def test_rejects_missing_and_unexpected_parameters(self) -> None:
        self._assert_invalid(
            self._request("files.search", {"root": str(self.safe_root)}),
            ActionFailureCategory.INVALID_PARAMETERS,
        )
        self._assert_invalid(
            self._request(
                "files.search",
                {
                    "root": str(self.safe_root),
                    "query": "report",
                    "command": "cmd.exe",
                },
            ),
            ActionFailureCategory.INVALID_PARAMETERS,
        )

    def test_rejects_wrong_parameter_type(self) -> None:
        self._assert_invalid(
            self._request(
                "files.search",
                {"root": str(self.safe_root), "query": True},
            ),
            ActionFailureCategory.INVALID_PARAMETERS,
        )

    def test_rejects_spotify_volume_outside_registered_bounds(self) -> None:
        for value in (-1, 101, True):
            with self.subTest(value=value):
                self._assert_invalid(
                    self._request(
                        "spotify.volume",
                        {"service": "spotify", "volume_percent": value},
                    ),
                    ActionFailureCategory.INVALID_PARAMETERS,
                )

    def test_rejects_spotify_seek_outside_registered_bounds(self) -> None:
        for value in (-1, 86401, False):
            with self.subTest(value=value):
                self._assert_invalid(
                    self._request(
                        "spotify.seek",
                        {"service": "spotify", "position_seconds": value},
                    ),
                    ActionFailureCategory.INVALID_PARAMETERS,
                )
        self._assert_invalid(
            self._request(
                "directories.search",
                {
                    "root": str(self.safe_root),
                    "query": "compressed",
                    "match_all": "yes",
                },
            ),
            ActionFailureCategory.INVALID_PARAMETERS,
        )
        self._assert_invalid(
            self._request(
                "files.search",
                {
                    "root": str(self.safe_root),
                    "query": "report",
                    "media_only": "true",
                },
            ),
            ActionFailureCategory.INVALID_PARAMETERS,
        )

    def test_rejects_protected_file_target(self) -> None:
        self._assert_invalid(
            self._request(
                "files.search",
                {"root": str(self.protected_root), "query": "config"},
            ),
            ActionFailureCategory.INVALID_TARGET,
        )

    def test_rejects_non_passive_file_target(self) -> None:
        executable = self.safe_root / "installer.exe"
        executable.write_text("not really executable", encoding="utf-8")
        self._assert_invalid(
            self._request("files.open", {"path": str(executable)}),
            ActionFailureCategory.INVALID_TARGET,
        )

    def test_rejects_application_outside_allowlist(self) -> None:
        self._assert_invalid(
            self._request(
                "applications.launch",
                {"application_id": "powershell"},
            ),
            ActionFailureCategory.INVALID_PARAMETERS,
        )

    def test_rejects_ai_supplied_application_path_or_arguments(self) -> None:
        self._assert_invalid(
            self._request(
                "applications.launch",
                {
                    "application_id": "chrome",
                    "path": r"C:\Windows\System32\cmd.exe",
                    "arguments": ["/c", "whoami"],
                },
            ),
            ActionFailureCategory.INVALID_PARAMETERS,
        )

    def test_requires_typed_action_request(self) -> None:
        with self.assertRaises(TypeError):
            self.validator.validate("open discord")  # type: ignore[arg-type]

    def _request(
        self,
        action_id: str,
        parameters: dict[str, object],
    ) -> ActionRequest:
        return ActionRequest(
            correlation_id="request-1",
            action_id=action_id,
            source="chat",
            parameters=parameters,
        )

    def _assert_invalid(
        self,
        request: ActionRequest,
        category: ActionFailureCategory,
    ) -> None:
        with self.assertRaises(ActionValidationError) as captured:
            self.validator.validate(request)
        self.assertEqual(captured.exception.category, category)


if __name__ == "__main__":
    unittest.main()
