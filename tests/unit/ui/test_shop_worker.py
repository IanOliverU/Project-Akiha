"""Tests for typed non-blocking shop UI operations."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from uuid import UUID

from project_akiha.core.shop import (
    AcquisitionSource,
    CatalogAvailability,
    CatalogQuery,
    EquipmentDecision,
    EquipmentOutcome,
    EquipmentSlot,
    PurchaseDecision,
    ShopBrowseResult,
    ShopInventoryItemView,
    ShopLoadoutView,
    ShopPurchaseResult,
)
from project_akiha.ui.shop_worker import (
    ShopOperationThread,
    ShopUiSnapshot,
    ShopWorkerOperation,
)

_NOW = datetime(2026, 8, 21, 18, 0, tzinfo=UTC)


class ShopOperationThreadTest(unittest.TestCase):
    """Verify workers dispatch only closed typed operations."""

    def test_refresh_reads_all_presentation_state_without_mutation(self) -> None:
        service = _FakeShopService()
        emitted: list[object] = []
        query = CatalogQuery()
        thread = ShopOperationThread(  # type: ignore[arg-type]
            service,
            ShopWorkerOperation.REFRESH,
            query=query,
        )
        thread.completed.connect(emitted.append)

        thread.run()

        self.assertEqual(service.mutations, [])
        self.assertEqual(service.queries, [query])
        self.assertEqual(len(emitted), 1)
        result = emitted[0]
        self.assertEqual(result.operation, ShopWorkerOperation.REFRESH)
        self.assertIsInstance(result.snapshot, ShopUiSnapshot)

    def test_purchase_returns_outcome_and_refreshed_snapshot(self) -> None:
        service = _FakeShopService()
        emitted: list[object] = []
        thread = ShopOperationThread(  # type: ignore[arg-type]
            service,
            ShopWorkerOperation.PURCHASE,
            item_id="ribbon.red",
        )
        thread.completed.connect(emitted.append)

        thread.run()

        self.assertEqual(service.mutations, [("purchase", "ribbon.red")])
        result = emitted[0]
        self.assertIs(result.purchase, service.purchase_result)
        self.assertEqual(service.reads, ["browse", "inventory", "loadout"])

    def test_equip_and_unequip_forward_only_typed_targets(self) -> None:
        service = _FakeShopService()
        equip = ShopOperationThread(  # type: ignore[arg-type]
            service,
            ShopWorkerOperation.EQUIP,
            item_id="ribbon.red",
        )
        unequip = ShopOperationThread(  # type: ignore[arg-type]
            service,
            ShopWorkerOperation.UNEQUIP,
            slot=EquipmentSlot.HEAD,
        )

        equip.run()
        unequip.run()

        self.assertEqual(
            service.mutations,
            [("equip", "ribbon.red"), ("unequip", EquipmentSlot.HEAD)],
        )

    def test_constructor_rejects_untyped_or_mismatched_arguments(self) -> None:
        service = _FakeShopService()
        with self.assertRaises(TypeError):
            ShopOperationThread(  # type: ignore[arg-type]
                service,
                "purchase",
                item_id="ribbon.red",
            )
        with self.assertRaises(ValueError):
            ShopOperationThread(  # type: ignore[arg-type]
                service,
                ShopWorkerOperation.PURCHASE,
            )
        with self.assertRaises(ValueError):
            ShopOperationThread(  # type: ignore[arg-type]
                service,
                ShopWorkerOperation.REFRESH,
                item_id="ribbon.red",
            )
        with self.assertRaises(TypeError):
            ShopOperationThread(  # type: ignore[arg-type]
                service,
                ShopWorkerOperation.UNEQUIP,
                slot="head",
            )


class _FakeShopService:
    def __init__(self) -> None:
        self.queries: list[CatalogQuery | None] = []
        self.reads: list[str] = []
        self.mutations: list[tuple[str, object]] = []
        self.purchase_result = ShopPurchaseResult(
            decision=PurchaseDecision.COMPLETED,
            item_id="ribbon.red",
            balance_before=100,
            balance_after=80,
            transaction_id=UUID("11111111-1111-1111-1111-111111111111"),
        )
        self.equipment_result = EquipmentOutcome(
            decision=EquipmentDecision.EQUIPPED,
            loadout=ShopLoadoutView(),
            slot=EquipmentSlot.HEAD,
            item_id="ribbon.red",
        )

    async def browse(self, query: CatalogQuery | None = None) -> ShopBrowseResult:
        self.queries.append(query)
        self.reads.append("browse")
        return ShopBrowseResult(
            catalog_version=1,
            catalog_failure=None,
            balance=80,
            level=2,
            items=(),
        )

    async def inventory(self) -> tuple[ShopInventoryItemView, ...]:
        self.reads.append("inventory")
        return (
            ShopInventoryItemView(
                item_id="ribbon.red",
                acquired_at=_NOW,
                acquisition_source=AcquisitionSource.PURCHASE,
                display_name="Red Ribbon",
                slot=EquipmentSlot.HEAD,
                availability=CatalogAvailability.AVAILABLE,
                visual_compatible=True,
                equipped=False,
                present_in_catalog=True,
            ),
        )

    async def loadout(self) -> ShopLoadoutView:
        self.reads.append("loadout")
        return ShopLoadoutView()

    async def purchase(self, item_id: str) -> ShopPurchaseResult:
        self.mutations.append(("purchase", item_id))
        return self.purchase_result

    async def equip(self, item_id: str) -> EquipmentOutcome:
        self.mutations.append(("equip", item_id))
        return self.equipment_result

    async def unequip(self, slot: EquipmentSlot) -> EquipmentOutcome:
        self.mutations.append(("unequip", slot))
        return EquipmentOutcome(
            decision=EquipmentDecision.UNEQUIPPED,
            loadout=ShopLoadoutView(),
            slot=slot,
            item_id="ribbon.red",
        )


if __name__ == "__main__":
    unittest.main()
