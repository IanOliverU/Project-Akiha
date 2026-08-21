"""Tests for fixed complete-appearance selection policy."""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from project_akiha.core.appearance import (
    AppearanceAvailability,
    AppearanceDefinition,
    AppearanceId,
    AppearanceRegistry,
    AppearanceSelection,
    AppearanceSelectionDecision,
)
from project_akiha.core.events import Event, EventBus, EventType
from project_akiha.core.shop import AcquisitionSource, InventoryItem
from project_akiha.services.appearance import AppearanceService

_NOW = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)


class _Clock:
    def now(self) -> datetime:
        return _NOW


class _AppearanceRepository:
    def __init__(self, selection: AppearanceSelection) -> None:
        self.selection = selection

    async def get_selection(self) -> AppearanceSelection:
        return self.selection

    async def save_selection(
        self, selection: AppearanceSelection
    ) -> AppearanceSelection:
        self.selection = selection
        return selection


class _ShopRepository:
    def __init__(self) -> None:
        self.inventory: dict[str, InventoryItem] = {}

    async def get_inventory_item(self, item_id: str) -> InventoryItem | None:
        return self.inventory.get(item_id)

    async def list_inventory(self) -> tuple[InventoryItem, ...]:
        return tuple(self.inventory.values())


class AppearanceServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        root = Path(self._temporary_directory.name)
        (root / "seifuku.toml").write_text("schema_version = 1", encoding="utf-8")
        (root / "dress.toml").write_text("schema_version = 1", encoding="utf-8")
        self._registry = AppearanceRegistry(
            root=root,
            default_appearance_id=AppearanceId.SEIFUKU,
            definitions=(
                AppearanceDefinition(
                    AppearanceId.SEIFUKU,
                    "Akiha - Seifuku",
                    AppearanceAvailability.AVAILABLE,
                    "seifuku.toml",
                    "seifuku-approval.toml",
                ),
                AppearanceDefinition(
                    AppearanceId.DRESS,
                    "Akiha - Dress",
                    AppearanceAvailability.AVAILABLE,
                    "dress.toml",
                    "dress-approval.toml",
                    required_item_id="appearance.dress",
                ),
                AppearanceDefinition(
                    AppearanceId.VERMILLION,
                    "Akiha Vermillion",
                    AppearanceAvailability.UNAVAILABLE,
                    required_item_id="appearance.vermillion",
                ),
            ),
        )
        self._appearance_repository = _AppearanceRepository(
            AppearanceSelection(AppearanceId.SEIFUKU, _NOW)
        )
        self._shop_repository = _ShopRepository()
        self._events: list[Event] = []
        event_bus = EventBus()
        event_bus.subscribe(EventType.APPEARANCE_CHANGED, self._events.append)
        self._service = AppearanceService(
            self._registry,
            self._appearance_repository,  # type: ignore[arg-type]
            self._shop_repository,  # type: ignore[arg-type]
            _Clock(),
            event_bus=event_bus,
        )
        await self._service.initialize()

    async def test_lists_fixed_appearances_without_asset_paths(self) -> None:
        appearances = await self._service.list_appearances()

        self.assertEqual(
            tuple(item.appearance_id for item in appearances), tuple(AppearanceId)
        )
        self.assertTrue(appearances[0].owned)
        self.assertTrue(appearances[0].selected)
        self.assertFalse(appearances[1].owned)
        self.assertFalse(appearances[2].owned)

    async def test_select_requires_available_assets_and_ownership(self) -> None:
        unowned = await self._service.select(AppearanceId.DRESS)
        unavailable = await self._service.select(AppearanceId.VERMILLION)
        self._shop_repository.inventory["appearance.dress"] = InventoryItem(
            "appearance.dress",
            _NOW,
            AcquisitionSource.REWARD,
        )
        selected = await self._service.select(AppearanceId.DRESS)
        repeated = await self._service.select(AppearanceId.DRESS)

        self.assertIs(unowned.decision, AppearanceSelectionDecision.NOT_OWNED)
        self.assertIs(unavailable.decision, AppearanceSelectionDecision.UNAVAILABLE)
        self.assertIs(selected.decision, AppearanceSelectionDecision.SELECTED)
        self.assertIs(repeated.decision, AppearanceSelectionDecision.ALREADY_SELECTED)
        self.assertIs(self._service.current_appearance_id, AppearanceId.DRESS)
        self.assertEqual(len(self._events), 1)
        self.assertNotIn("path", self._events[0].payload)

    async def test_initialize_repairs_stale_ineligible_selection(self) -> None:
        self._appearance_repository.selection = AppearanceSelection(
            AppearanceId.DRESS,
            _NOW,
        )
        repaired = await AppearanceService(
            self._registry,
            self._appearance_repository,  # type: ignore[arg-type]
            self._shop_repository,  # type: ignore[arg-type]
            _Clock(),
        ).initialize()

        self.assertIs(repaired.appearance_id, AppearanceId.SEIFUKU)


if __name__ == "__main__":
    unittest.main()
