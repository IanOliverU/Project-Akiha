"""Tests for immutable action contracts and the application registry."""

from __future__ import annotations

import unittest

from project_akiha.core.actions import (
    ActionFailureCategory,
    ActionRequest,
    ActionValidationError,
    build_default_action_registry,
)


class ActionModelsAndRegistryTest(unittest.TestCase):
    """Verify action proposals cannot alter application-owned definitions."""

    def test_request_copies_and_freezes_parameters(self) -> None:
        parameters: dict[str, object] = {"application_id": "spotify"}
        request = ActionRequest(
            correlation_id="request-1",
            action_id="applications.launch",
            source="chat",
            parameters=parameters,
        )

        parameters["application_id"] = "chrome"

        self.assertEqual(request.parameters["application_id"], "spotify")
        with self.assertRaises(TypeError):
            request.parameters["application_id"] = "discord"  # type: ignore[index]

    def test_default_registry_contains_only_initial_allowlisted_actions(self) -> None:
        registry = build_default_action_registry()

        self.assertEqual(
            tuple(item.action_id for item in registry.definitions),
            (
                "files.search",
                "files.open_directory",
                "files.open",
                "applications.launch",
            ),
        )

    def test_unknown_action_is_rejected_with_safe_category(self) -> None:
        registry = build_default_action_registry()

        with self.assertRaises(ActionValidationError) as captured:
            registry.resolve("system.run")

        self.assertEqual(
            captured.exception.category,
            ActionFailureCategory.UNKNOWN_ACTION,
        )

    def test_request_rejects_audit_unsafe_identifiers(self) -> None:
        with self.assertRaises(ValueError):
            ActionRequest(
                correlation_id="request\n1",
                action_id="applications.launch",
                source="chat",
                parameters={"application_id": "spotify"},
            )
        with self.assertRaises(ValueError):
            ActionRequest(
                correlation_id="request-1",
                action_id="RUN THIS",
                source="chat",
                parameters={},
            )


if __name__ == "__main__":
    unittest.main()
