"""Tests for the explicit provider-facing assistant-action catalog."""

from __future__ import annotations

import unittest

from project_akiha.core.actions import (
    DEFAULT_PROVIDER_ACTION_IDS,
    ActionDefinition,
    ActionFailureCategory,
    ActionParameterSpec,
    ActionRegistry,
    ActionRisk,
    ActionValidationError,
    ConfirmationPolicy,
    ParameterKind,
    ProviderActionToolCatalog,
    build_default_action_registry,
    build_default_provider_action_catalog,
)


class ProviderActionToolCatalogTest(unittest.TestCase):
    def test_default_catalog_exposes_only_explicit_action_ids(self) -> None:
        registry = build_default_action_registry()
        extra = _definition("future.safe_action")
        extended = ActionRegistry((*registry.definitions, extra))

        catalog = build_default_provider_action_catalog(extended)

        self.assertEqual(
            tuple(schema.action_id for schema in catalog.schemas),
            DEFAULT_PROVIDER_ACTION_IDS,
        )
        with self.assertRaises(ActionValidationError) as captured:
            catalog.resolve(extra.action_id)
        self.assertEqual(
            captured.exception.category,
            ActionFailureCategory.UNKNOWN_ACTION,
        )

    def test_schema_preserves_bounded_parameter_constraints(self) -> None:
        catalog = build_default_provider_action_catalog()

        schema = catalog.resolve("applications.launch")

        self.assertEqual(schema.action_id, "applications.launch")
        self.assertEqual(len(schema.parameters), 1)
        parameter = schema.parameters[0]
        self.assertEqual(parameter.name, "application_id")
        self.assertEqual(parameter.kind, ParameterKind.STRING)
        self.assertTrue(parameter.required)
        self.assertIn("spotify", parameter.allowed_values)
        self.assertFalse(hasattr(schema, "executor_id"))
        self.assertFalse(hasattr(schema, "permission_capability"))

    def test_catalog_rejects_unknown_duplicate_and_prohibited_exposure(self) -> None:
        registry = build_default_action_registry()

        with self.assertRaises(ActionValidationError):
            ProviderActionToolCatalog(registry, ("system.run",))
        with self.assertRaisesRegex(ValueError, "duplicate provider action"):
            ProviderActionToolCatalog(
                registry,
                ("applications.launch", "applications.launch"),
            )

        prohibited = _definition("system.run", risk=ActionRisk.PROHIBITED)
        with self.assertRaisesRegex(ValueError, "prohibited actions"):
            ProviderActionToolCatalog(
                ActionRegistry((prohibited,)),
                (prohibited.action_id,),
            )


def _definition(
    action_id: str,
    *,
    risk: ActionRisk = ActionRisk.READ_ONLY,
) -> ActionDefinition:
    return ActionDefinition(
        action_id=action_id,
        description="A test-only action.",
        risk=risk,
        permission_capability="test.permission",
        confirmation_policy=ConfirmationPolicy.NEVER,
        executor_id="test_executor",
        target_parameter="target",
        parameters=(
            ActionParameterSpec(
                name="target",
                kind=ParameterKind.STRING,
                max_length=64,
            ),
        ),
        timeout_seconds=1,
    )


if __name__ == "__main__":
    unittest.main()
