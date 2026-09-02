"""Tests for the non-executable Phase 13 utility contract catalog."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from project_akiha.core.actions import (
    DIRECTORY_SEARCH_ACTION,
    OPEN_DIRECTORY_ACTION,
    build_default_action_registry,
)
from project_akiha.core.utilities import (
    UtilityAuthorization,
    UtilityContractCatalog,
    UtilityEffect,
    UtilityNetworkAccess,
    UtilityOperation,
    UtilityOperationContract,
    UtilityOwner,
    UtilityReasonCode,
    UtilityResult,
    UtilityResultStatus,
    UtilityStorage,
    build_phase_13_utility_catalog,
)


class UtilityContractCatalogTest(unittest.TestCase):
    def test_utility_core_remains_framework_and_adapter_free(self) -> None:
        utilities_dir = Path(__file__).parents[4] / "project_akiha/core/utilities"
        forbidden_prefixes = (
            "PySide6",
            "project_akiha.app",
            "project_akiha.database",
            "project_akiha.integrations",
            "project_akiha.providers",
            "project_akiha.services",
            "project_akiha.ui",
        )

        for path in utilities_dir.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported_modules = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_modules.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module is not None:
                    imported_modules.append(node.module)
            with self.subTest(path=path.name):
                self.assertFalse(
                    any(
                        module.startswith(forbidden_prefixes)
                        for module in imported_modules
                    )
                )

    def test_catalog_declares_every_approved_operation_once(self) -> None:
        catalog = build_phase_13_utility_catalog()

        self.assertEqual(len(catalog.contracts), len(UtilityOperation))
        self.assertEqual(
            {contract.operation for contract in catalog.contracts},
            set(UtilityOperation),
        )

    def test_navigation_reuses_existing_action_ids_and_scoped_grants(self) -> None:
        catalog = build_phase_13_utility_catalog()
        search = catalog.resolve(UtilityOperation.NAVIGATION_SEARCH)
        open_directory = catalog.resolve(UtilityOperation.NAVIGATION_OPEN)

        self.assertEqual(search.action_id, DIRECTORY_SEARCH_ACTION)
        self.assertEqual(open_directory.action_id, OPEN_DIRECTORY_ACTION)
        self.assertTrue(search.requires_approved_root)
        self.assertTrue(open_directory.requires_approved_root)
        self.assertEqual(search.authorization, UtilityAuthorization.SCOPED_GRANT)
        self.assertEqual(search.network_access, UtilityNetworkAccess.NONE)

    def test_schedule_operations_have_one_owner_and_no_network_access(self) -> None:
        contracts = build_phase_13_utility_catalog().contracts
        schedules = tuple(
            contract
            for contract in contracts
            if contract.operation.value.startswith(("timers.", "reminders."))
        )

        self.assertTrue(schedules)
        self.assertTrue(
            all(
                contract.owner is UtilityOwner.SCHEDULE_SERVICE
                for contract in schedules
            )
        )
        self.assertTrue(
            all(
                contract.storage is UtilityStorage.SCHEDULE_METADATA
                for contract in schedules
            )
        )
        self.assertTrue(
            all(
                contract.network_access is UtilityNetworkAccess.NONE
                for contract in schedules
            )
        )

    def test_only_weather_contracts_allow_read_only_network_access(self) -> None:
        networked = tuple(
            contract
            for contract in build_phase_13_utility_catalog().contracts
            if contract.network_access is not UtilityNetworkAccess.NONE
        )

        self.assertEqual(
            {contract.operation for contract in networked},
            {
                UtilityOperation.WEATHER_CURRENT,
                UtilityOperation.WEATHER_FORECAST,
            },
        )
        self.assertTrue(
            all(contract.effect is UtilityEffect.READ_ONLY for contract in networked)
        )

    def test_exports_require_current_confirmation_and_local_destination(self) -> None:
        contracts = build_phase_13_utility_catalog().contracts
        exports = tuple(
            contract
            for contract in contracts
            if contract.owner is UtilityOwner.EXPORT_SERVICE
        )

        self.assertEqual(len(exports), 2)
        self.assertTrue(
            all(
                contract.authorization is UtilityAuthorization.CONFIRM_EACH_TIME
                for contract in exports
            )
        )
        self.assertTrue(
            all(
                contract.effect is UtilityEffect.USER_SELECTED_FILE_WRITE
                for contract in exports
            )
        )
        self.assertTrue(
            all(
                contract.storage is UtilityStorage.USER_SELECTED_EXPORT
                for contract in exports
            )
        )

    def test_future_actions_are_not_exposed_before_their_executor_exists(self) -> None:
        active_ids = {
            definition.action_id
            for definition in build_default_action_registry().definitions
        }

        self.assertIn(UtilityOperation.NAVIGATION_SEARCH.value, active_ids)
        self.assertIn(UtilityOperation.NAVIGATION_OPEN.value, active_ids)
        self.assertNotIn(UtilityOperation.TIMER_CREATE.value, active_ids)
        self.assertNotIn(UtilityOperation.WEATHER_CURRENT.value, active_ids)
        self.assertNotIn(UtilityOperation.EXPORT_CONVERSATIONS.value, active_ids)

    def test_catalog_rejects_duplicate_and_unknown_operations(self) -> None:
        contract = _read_only_contract(UtilityOperation.WEATHER_CURRENT)

        with self.assertRaises(ValueError):
            UtilityContractCatalog((contract, contract))
        with self.assertRaises(ValueError):
            UtilityContractCatalog((contract,)).resolve_action("shell.execute")
        with self.assertRaises(TypeError):
            UtilityContractCatalog((contract,)).resolve("timers.create")  # type: ignore[arg-type]

    def test_contract_rejects_networked_mutation(self) -> None:
        with self.assertRaises(ValueError):
            UtilityOperationContract(
                operation=UtilityOperation.TIMER_CREATE,
                owner=UtilityOwner.SCHEDULE_SERVICE,
                effect=UtilityEffect.LOCAL_SCHEDULE,
                authorization=UtilityAuthorization.REQUEST_BOUND,
                network_access=UtilityNetworkAccess.READ_ONLY,
                storage=UtilityStorage.SCHEDULE_METADATA,
            )

    def test_contract_rejects_unconfirmed_export_write(self) -> None:
        with self.assertRaises(ValueError):
            UtilityOperationContract(
                operation=UtilityOperation.EXPORT_CONVERSATIONS,
                owner=UtilityOwner.EXPORT_SERVICE,
                effect=UtilityEffect.USER_SELECTED_FILE_WRITE,
                authorization=UtilityAuthorization.REQUEST_BOUND,
                network_access=UtilityNetworkAccess.NONE,
                storage=UtilityStorage.USER_SELECTED_EXPORT,
            )


class UtilityResultTest(unittest.TestCase):
    def test_result_keeps_bounded_scalar_metadata_immutable(self) -> None:
        metadata: dict[str, str | int | float | bool | None] = {
            "timer_id": "timer-1",
            "duration_seconds": 60,
        }
        result = UtilityResult(
            correlation_id="turn-1",
            operation=UtilityOperation.TIMER_CREATE,
            status=UtilityResultStatus.SUCCESS,
            reason=UtilityReasonCode.COMPLETED,
            summary="Timer created.",
            metadata=metadata,
        )
        metadata["timer_id"] = "changed"

        self.assertEqual(result.metadata["timer_id"], "timer-1")
        with self.assertRaises(TypeError):
            result.metadata["timer_id"] = "changed"  # type: ignore[index]

    def test_result_rejects_status_reason_mismatch(self) -> None:
        with self.assertRaises(ValueError):
            UtilityResult(
                correlation_id="turn-1",
                operation=UtilityOperation.WEATHER_CURRENT,
                status=UtilityResultStatus.SUCCESS,
                reason=UtilityReasonCode.NETWORK_FAILURE,
                summary="Weather loaded.",
            )

    def test_result_rejects_nested_or_oversized_metadata(self) -> None:
        with self.assertRaises(TypeError):
            UtilityResult(
                correlation_id="turn-1",
                operation=UtilityOperation.WEATHER_CURRENT,
                status=UtilityResultStatus.SUCCESS,
                reason=UtilityReasonCode.COMPLETED,
                summary="Weather loaded.",
                metadata={"provider_payload": {"raw": "blocked"}},  # type: ignore[dict-item]
            )
        with self.assertRaises(ValueError):
            UtilityResult(
                correlation_id="turn-1",
                operation=UtilityOperation.WEATHER_CURRENT,
                status=UtilityResultStatus.SUCCESS,
                reason=UtilityReasonCode.COMPLETED,
                summary="Weather loaded.",
                metadata={f"field_{index}": index for index in range(17)},
            )


def _read_only_contract(operation: UtilityOperation) -> UtilityOperationContract:
    return UtilityOperationContract(
        operation=operation,
        owner=UtilityOwner.CURRENT_INFORMATION_PROVIDER,
        effect=UtilityEffect.READ_ONLY,
        authorization=UtilityAuthorization.REQUEST_BOUND,
        network_access=UtilityNetworkAccess.READ_ONLY,
        storage=UtilityStorage.NONE,
    )


if __name__ == "__main__":
    unittest.main()
