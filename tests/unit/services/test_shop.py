"""Tests for typed shop, inventory, and wardrobe orchestration."""

from __future__ import annotations

import unittest
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.core.events import Event, EventBus, EventType
from project_akiha.core.pet import PetProgression, PetState
from project_akiha.core.shop import (
    CatalogLoadFailure,
    CatalogLoadResult,
    CatalogOwnershipFilter,
    CatalogQuery,
    EquipmentDecision,
    EquipmentSlot,
    PurchaseDecision,
    ShopCatalog,
    ShopInspectDecision,
    parse_catalog_toml,
)
from project_akiha.database import SQLitePetStateRepository, SQLiteShopRepository
from project_akiha.services.pet_state import PetStateService
from project_akiha.services.shop import ShopService

_CATALOG = """
schema_version = 1
catalog_version = 1

[[layers]]
layer_id = "ribbon.red.layer"
asset_path = "head/ribbon-red/idle.png"
states = ["idle", "walking"]
directions = ["left", "right"]

[[layers]]
layer_id = "ribbon.blue.layer"
asset_path = "head/ribbon-blue/idle.png"
states = ["idle"]
directions = ["left", "right"]

[[layers]]
layer_id = "glasses.black.layer"
asset_path = "face/glasses-black/idle.png"
states = ["idle"]
directions = ["right"]

[[layers]]
layer_id = "brooch.gold.layer"
asset_path = "accessory/brooch-gold/idle.png"
states = ["idle"]
directions = ["left", "right"]

[[layers]]
layer_id = "crown.level.layer"
asset_path = "head/crown-level/idle.png"
states = ["idle"]
directions = ["left", "right"]

[[items]]
item_id = "ribbon.red"
display_name = "Red Ribbon"
category = "cosmetic"
slot = "head"
price = 20
availability = "available"
required_level = 1
preview_asset_id = "ribbon.red.layer"
cosmetic_layer_id = "ribbon.red.layer"

[[items]]
item_id = "ribbon.blue"
display_name = "Blue Ribbon"
category = "cosmetic"
slot = "head"
price = 25
availability = "available"
required_level = 1
preview_asset_id = "ribbon.blue.layer"
cosmetic_layer_id = "ribbon.blue.layer"

[[items]]
item_id = "glasses.black"
display_name = "Black Glasses"
category = "cosmetic"
slot = "face"
price = 30
availability = "available"
required_level = 1
preview_asset_id = "glasses.black.layer"
cosmetic_layer_id = "glasses.black.layer"

[[items]]
item_id = "brooch.gold"
display_name = "Gold Brooch"
category = "cosmetic"
slot = "accessory"
price = 10
availability = "hidden"
required_level = 1
preview_asset_id = "brooch.gold.layer"
cosmetic_layer_id = "brooch.gold.layer"

[[items]]
item_id = "crown.level"
display_name = "Level Crown"
category = "cosmetic"
slot = "head"
price = 200
availability = "available"
required_level = 2
preview_asset_id = "crown.level.layer"
cosmetic_layer_id = "crown.level.layer"
"""


class _FakeClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


class ShopServiceTest(unittest.IsolatedAsyncioTestCase):
    """Verify service policy with real persistence and pet-state reconciliation."""

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
        self._events: list[Event] = []
        self._event_bus = EventBus()
        self._event_bus.subscribe(
            EventType.SHOP_PURCHASE_COMPLETED,
            self._events.append,
        )
        self._event_bus.subscribe(
            EventType.SHOP_EQUIPMENT_CHANGED,
            self._events.append,
        )
        self._service = ShopService(
            CatalogLoadResult(self._catalog),
            self._shop_repository,
            self._pet_service,
            self._clock,
            event_bus=self._event_bus,
        )

    async def test_browse_and_inspect_return_sanitized_catalog_state(self) -> None:
        browse = await self._service.browse()
        inspected = await self._service.inspect("ribbon.red")
        missing = await self._service.inspect("unknown.item")

        self.assertEqual(browse.balance, 100)
        self.assertEqual(browse.level, 1)
        self.assertEqual(len(browse.items), 4)
        self.assertNotIn("brooch.gold", {item.item_id for item in browse.items})
        ribbon = next(item for item in browse.items if item.item_id == "ribbon.red")
        self.assertTrue(ribbon.affordable)
        self.assertTrue(ribbon.level_met)
        self.assertTrue(ribbon.visual_compatible)
        self.assertFalse(ribbon.owned)
        glasses = next(item for item in browse.items if item.item_id == "glasses.black")
        self.assertFalse(glasses.visual_compatible)
        self.assertIs(inspected.decision, ShopInspectDecision.FOUND)
        self.assertIs(missing.decision, ShopInspectDecision.ITEM_NOT_FOUND)
        self.assertIsNone(missing.item)
        self.assertNotIn("path", repr(asdict(inspected)))
        self.assertNotIn("asset", repr(asdict(inspected)))

    async def test_browse_applies_typed_ownership_filter(self) -> None:
        await self._service.purchase("ribbon.red")

        owned = await self._service.browse(
            CatalogQuery(ownership=CatalogOwnershipFilter.OWNED)
        )

        self.assertEqual(tuple(item.item_id for item in owned.items), ("ribbon.red",))
        self.assertTrue(owned.items[0].owned)
        self.assertEqual(owned.balance, 80)

    async def test_completed_purchase_refreshes_pet_cache_and_publishes_safely(
        self,
    ) -> None:
        result = await self._service.purchase("ribbon.red")
        pet_snapshot = await self._pet_service.snapshot()

        self.assertIs(result.decision, PurchaseDecision.COMPLETED)
        self.assertEqual(result.balance_after, 80)
        self.assertEqual(pet_snapshot.state.progression.currency, 80)
        self.assertEqual(len(self._events), 1)
        event = self._events[0]
        self.assertIs(event.event_type, EventType.SHOP_PURCHASE_COMPLETED)
        self.assertEqual(event.payload["item_id"], "ribbon.red")
        self.assertNotIn("path", event.payload)
        self.assertNotIn("asset", event.payload)
        self.assertNotIn("price", event.payload)

    async def test_denied_purchases_do_not_publish_mutation_events(self) -> None:
        missing = await self._service.purchase("unknown.item")
        hidden = await self._service.purchase("brooch.gold")
        level = await self._service.purchase("crown.level")

        self.assertIs(missing.decision, PurchaseDecision.ITEM_NOT_FOUND)
        self.assertIs(hidden.decision, PurchaseDecision.ITEM_UNAVAILABLE)
        self.assertIs(level.decision, PurchaseDecision.LEVEL_REQUIRED)
        self.assertEqual(self._events, [])
        self.assertEqual(
            (await self._pet_service.snapshot()).state.progression.currency, 100
        )
        self.assertEqual(await self._service.inventory(), ())

    async def test_equip_requires_ownership_and_visual_compatibility(self) -> None:
        unowned = await self._service.equip("ribbon.red")
        missing = await self._service.equip("unknown.item")
        await self._service.purchase("glasses.black")
        incompatible = await self._service.equip("glasses.black")
        inventory = await self._service.inventory()

        self.assertIs(unowned.decision, EquipmentDecision.NOT_OWNED)
        self.assertIs(missing.decision, EquipmentDecision.ITEM_NOT_FOUND)
        self.assertIs(
            incompatible.decision,
            EquipmentDecision.VISUAL_INCOMPATIBLE,
        )
        glasses = next(item for item in inventory if item.item_id == "glasses.black")
        self.assertFalse(glasses.visual_compatible)
        self.assertEqual(
            [event.event_type for event in self._events],
            [EventType.SHOP_PURCHASE_COMPLETED],
        )

    async def test_equip_replace_and_unequip_preserve_inventory(self) -> None:
        await self._service.purchase("ribbon.red")
        await self._service.purchase("ribbon.blue")
        first = await self._service.equip("ribbon.red")
        repeated = await self._service.equip("ribbon.red")
        replacement = await self._service.equip("ribbon.blue")
        removed = await self._service.unequip(EquipmentSlot.HEAD)
        empty = await self._service.unequip(EquipmentSlot.HEAD)
        inventory = await self._service.inventory()

        self.assertIs(first.decision, EquipmentDecision.EQUIPPED)
        self.assertIs(repeated.decision, EquipmentDecision.ALREADY_EQUIPPED)
        self.assertIs(replacement.decision, EquipmentDecision.EQUIPPED)
        self.assertEqual(
            replacement.loadout.item_for(EquipmentSlot.HEAD).item_id,  # type: ignore[union-attr]
            "ribbon.blue",
        )
        self.assertIs(removed.decision, EquipmentDecision.UNEQUIPPED)
        self.assertIs(empty.decision, EquipmentDecision.EMPTY_SLOT)
        self.assertEqual(
            {item.item_id for item in inventory}, {"ribbon.red", "ribbon.blue"}
        )
        self.assertFalse(any(item.equipped for item in inventory))
        equipment_events = [
            event
            for event in self._events
            if event.event_type is EventType.SHOP_EQUIPMENT_CHANGED
        ]
        self.assertEqual(len(equipment_events), 3)

    async def test_orphaned_inventory_remains_visible_after_catalog_change(
        self,
    ) -> None:
        await self._service.purchase("ribbon.red")
        await self._service.equip("ribbon.red")
        empty_catalog_service = ShopService(
            CatalogLoadResult(
                ShopCatalog.empty(),
                failure=CatalogLoadFailure.INVALID_SCHEMA,
            ),
            self._shop_repository,
            self._pet_service,
            self._clock,
        )

        inventory = await empty_catalog_service.inventory()
        loadout = await empty_catalog_service.loadout()
        browse = await empty_catalog_service.browse()

        self.assertEqual(len(inventory), 1)
        self.assertEqual(inventory[0].item_id, "ribbon.red")
        self.assertFalse(inventory[0].present_in_catalog)
        self.assertIsNone(inventory[0].display_name)
        self.assertIsNone(inventory[0].availability)
        self.assertIsNone(inventory[0].visual_compatible)
        equipped = loadout.item_for(EquipmentSlot.HEAD)
        self.assertIsNotNone(equipped)
        assert equipped is not None
        self.assertFalse(equipped.present_in_catalog)
        self.assertEqual(browse.items, ())
        self.assertIs(browse.catalog_failure, CatalogLoadFailure.INVALID_SCHEMA)

    async def test_service_rejects_untyped_commands_and_clock_results(self) -> None:
        with self.assertRaises(TypeError):
            await self._service.browse("cheap")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            await self._service.equip(1)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            await self._service.unequip("head")  # type: ignore[arg-type]

        bad_clock = _FakeClock(datetime(2026, 8, 21, 15, 0))
        service = ShopService(
            CatalogLoadResult(self._catalog),
            self._shop_repository,
            self._pet_service,
            bad_clock,
        )
        with self.assertRaises(ValueError):
            await service.purchase("ribbon.red")


if __name__ == "__main__":
    unittest.main()
