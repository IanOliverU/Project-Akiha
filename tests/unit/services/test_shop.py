"""Tests for typed shop and complete-appearance ownership orchestration."""

from __future__ import annotations

import unittest
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.core.appearance import AppearanceId
from project_akiha.core.events import Event, EventBus, EventType
from project_akiha.core.pet import PetProgression, PetState
from project_akiha.core.shop import (
    CatalogLoadFailure,
    CatalogLoadResult,
    CatalogOwnershipFilter,
    CatalogQuery,
    PurchaseDecision,
    ShopCatalog,
    ShopInspectDecision,
    parse_catalog_toml,
)
from project_akiha.database import SQLitePetStateRepository, SQLiteShopRepository
from project_akiha.services.pet_state import PetStateService
from project_akiha.services.shop import ShopService

_CATALOG = """
schema_version = 2
catalog_version = 1

[[items]]
item_id = "appearance.dress"
display_name = "Akiha - Dress"
category = "appearance"
appearance_id = "dress"
price = 20
availability = "available"
required_level = 1

[[items]]
item_id = "appearance.vermillion"
display_name = "Akiha Vermillion"
category = "appearance"
appearance_id = "vermillion"
price = 30
availability = "available"
required_level = 1
"""


class _FakeClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


class _FakeAppearanceService:
    current_appearance_id = AppearanceId.SEIFUKU

    def asset_available(self, appearance_id: AppearanceId) -> bool:
        return appearance_id is AppearanceId.DRESS


class ShopServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._temporary_directory = TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self._database_path = Path(self._temporary_directory.name) / "akiha.sqlite3"
        self._clock = _FakeClock(datetime(2026, 8, 21, 15, 0, tzinfo=UTC))
        self._pet_repository = SQLitePetStateRepository(self._database_path)
        await self._pet_repository.load_or_create(
            PetState(progression=PetProgression(currency=100)),
            self._clock.now(),
        )
        self._pet_service = PetStateService(self._pet_repository, self._clock)
        await self._pet_service.initialize()
        self._shop_repository = SQLiteShopRepository(self._database_path)
        self._catalog = parse_catalog_toml(_CATALOG)
        self._appearance_service = _FakeAppearanceService()
        self._events: list[Event] = []
        self._event_bus = EventBus()
        self._event_bus.subscribe(
            EventType.SHOP_PURCHASE_COMPLETED, self._events.append
        )
        self._service = ShopService(
            CatalogLoadResult(self._catalog),
            self._shop_repository,
            self._pet_service,
            self._appearance_service,
            self._clock,
            event_bus=self._event_bus,
        )

    async def test_browse_and_inspect_return_sanitized_appearance_state(self) -> None:
        browse = await self._service.browse()
        inspected = await self._service.inspect("appearance.dress")
        missing = await self._service.inspect("unknown.item")

        self.assertEqual((browse.balance, browse.level), (100, 1))
        self.assertEqual(len(browse.items), 2)
        dress = next(
            item for item in browse.items if item.item_id == "appearance.dress"
        )
        vermillion = next(
            item for item in browse.items if item.item_id == "appearance.vermillion"
        )
        self.assertTrue(dress.asset_available)
        self.assertFalse(vermillion.asset_available)
        self.assertFalse(dress.owned)
        self.assertIs(inspected.decision, ShopInspectDecision.FOUND)
        self.assertIs(missing.decision, ShopInspectDecision.ITEM_NOT_FOUND)
        self.assertNotIn("manifest", repr(asdict(inspected)))
        self.assertNotIn("path", repr(asdict(inspected)))

    async def test_purchase_refreshes_currency_and_publishes_bounded_event(
        self,
    ) -> None:
        result = await self._service.purchase("appearance.dress")

        self.assertIs(result.decision, PurchaseDecision.COMPLETED)
        self.assertEqual(result.balance_after, 80)
        self.assertEqual(
            (await self._pet_service.snapshot()).state.progression.currency,
            80,
        )
        self.assertEqual(len(self._events), 1)
        self.assertEqual(self._events[0].payload["item_id"], "appearance.dress")
        self.assertNotIn("manifest", self._events[0].payload)

    async def test_unapproved_assets_fail_before_currency_mutation(self) -> None:
        unavailable = await self._service.purchase("appearance.vermillion")
        missing = await self._service.purchase("unknown.item")

        self.assertIs(unavailable.decision, PurchaseDecision.ITEM_UNAVAILABLE)
        self.assertIs(missing.decision, PurchaseDecision.ITEM_NOT_FOUND)
        self.assertEqual(
            (await self._pet_service.snapshot()).state.progression.currency,
            100,
        )
        self.assertEqual(await self._service.inventory(), ())
        self.assertEqual(self._events, [])

    async def test_owned_filter_and_orphaned_inventory_remain_stable(self) -> None:
        await self._service.purchase("appearance.dress")
        owned = await self._service.browse(
            CatalogQuery(ownership=CatalogOwnershipFilter.OWNED)
        )
        fallback = ShopService(
            CatalogLoadResult(
                ShopCatalog.empty(),
                failure=CatalogLoadFailure.INVALID_SCHEMA,
            ),
            self._shop_repository,
            self._pet_service,
            self._appearance_service,
            self._clock,
        )
        inventory = await fallback.inventory()

        self.assertEqual(
            tuple(item.item_id for item in owned.items), ("appearance.dress",)
        )
        self.assertEqual(inventory[0].item_id, "appearance.dress")
        self.assertFalse(inventory[0].present_in_catalog)
        self.assertIsNone(inventory[0].appearance_id)

    async def test_service_rejects_untyped_commands_and_bad_clock(self) -> None:
        with self.assertRaises(TypeError):
            await self._service.browse("cheap")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            await self._service.purchase(1)  # type: ignore[arg-type]

        service = ShopService(
            CatalogLoadResult(self._catalog),
            self._shop_repository,
            self._pet_service,
            self._appearance_service,
            _FakeClock(datetime(2026, 8, 21, 15, 0)),
        )
        with self.assertRaises(ValueError):
            await service.purchase("appearance.dress")


if __name__ == "__main__":
    unittest.main()
