"""Tests for trusted shop, inventory, economy, and cosmetic contracts."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from uuid import uuid4

from project_akiha.core.shop import (
    AcquisitionSource,
    CatalogAvailability,
    CatalogItem,
    CosmeticLayer,
    EquipmentLoadout,
    EquipmentSlot,
    EquippedItem,
    FacingDirection,
    InventoryItem,
    PurchaseDecision,
    PurchaseOutcome,
    PurchaseTransaction,
    ShopItemCategory,
)
from project_akiha.core.state.animation import AnimationState

_NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


def _catalog_item(**changes: object) -> CatalogItem:
    values: dict[str, object] = {
        "item_id": "starter.ribbon",
        "display_name": "Akiha Ribbon",
        "category": ShopItemCategory.COSMETIC,
        "slot": EquipmentSlot.HEAD,
        "price": 20,
        "availability": CatalogAvailability.AVAILABLE,
        "required_level": 1,
        "catalog_version": 1,
        "preview_asset_id": "starter.ribbon.preview",
        "cosmetic_layer_id": "starter.ribbon.layer",
    }
    values.update(changes)
    return CatalogItem(**values)  # type: ignore[arg-type]


class CatalogItemTest(unittest.TestCase):
    """Verify trusted catalog fields and progression prerequisites."""

    def test_accepts_initial_cosmetic_contract(self) -> None:
        item = _catalog_item()

        self.assertEqual(item.price, 20)
        self.assertEqual(item.required_level, 1)
        self.assertIs(item.slot, EquipmentSlot.HEAD)

    def test_rejects_unstable_ids_invalid_prices_and_levels(self) -> None:
        invalid_factories = (
            lambda: _catalog_item(item_id="Starter Ribbon"),
            lambda: _catalog_item(item_id="../ribbon"),
            lambda: _catalog_item(display_name=" Akiha Ribbon"),
            lambda: _catalog_item(price=-1),
            lambda: _catalog_item(price=True),
            lambda: _catalog_item(required_level=0),
            lambda: _catalog_item(catalog_version=False),
            lambda: _catalog_item(slot="head"),
        )

        for factory in invalid_factories:
            with self.subTest(factory=factory):
                with self.assertRaises((TypeError, ValueError)):
                    factory()


class InventoryAndLoadoutTest(unittest.TestCase):
    """Verify ownership provenance and single-slot equipment rules."""

    def test_purchase_inventory_requires_matching_transaction_provenance(self) -> None:
        transaction_id = uuid4()
        item = InventoryItem(
            item_id="starter.ribbon",
            acquired_at=_NOW,
            acquisition_source=AcquisitionSource.PURCHASE,
            purchase_transaction_id=transaction_id,
        )

        self.assertEqual(item.purchase_transaction_id, transaction_id)

        with self.assertRaises(ValueError):
            InventoryItem(
                item_id="starter.ribbon",
                acquired_at=_NOW,
                acquisition_source=AcquisitionSource.PURCHASE,
            )
        with self.assertRaises(ValueError):
            InventoryItem(
                item_id="starter.ribbon",
                acquired_at=_NOW,
                acquisition_source=AcquisitionSource.STARTER,
                purchase_transaction_id=transaction_id,
            )

    def test_loadout_rejects_duplicate_slots_and_item_ids(self) -> None:
        head = EquippedItem(EquipmentSlot.HEAD, "starter.ribbon", _NOW)
        second_head = EquippedItem(EquipmentSlot.HEAD, "formal.ribbon", _NOW)
        same_item_elsewhere = EquippedItem(
            EquipmentSlot.ACCESSORY,
            "starter.ribbon",
            _NOW,
        )

        with self.assertRaises(ValueError):
            EquipmentLoadout((head, second_head))
        with self.assertRaises(ValueError):
            EquipmentLoadout((head, same_item_elsewhere))

    def test_loadout_returns_item_by_typed_slot(self) -> None:
        head = EquippedItem(EquipmentSlot.HEAD, "starter.ribbon", _NOW)
        loadout = EquipmentLoadout((head,))

        self.assertEqual(loadout.item_for(EquipmentSlot.HEAD), head)
        self.assertIsNone(loadout.item_for(EquipmentSlot.FACE))
        with self.assertRaises(TypeError):
            loadout.item_for("head")  # type: ignore[arg-type]


class PurchaseContractTest(unittest.TestCase):
    """Verify atomic purchase arithmetic and no-mutation denials."""

    def test_completed_purchase_links_currency_and_inventory_records(self) -> None:
        transaction_id = uuid4()
        transaction = PurchaseTransaction(
            transaction_id=transaction_id,
            item_id="starter.ribbon",
            price=20,
            balance_before=25,
            balance_after=5,
            purchased_at=_NOW,
        )
        inventory = InventoryItem(
            item_id="starter.ribbon",
            acquired_at=_NOW,
            acquisition_source=AcquisitionSource.PURCHASE,
            purchase_transaction_id=transaction_id,
        )

        outcome = PurchaseOutcome(
            decision=PurchaseDecision.COMPLETED,
            balance_before=25,
            balance_after=5,
            transaction=transaction,
            inventory_item=inventory,
        )

        self.assertIs(outcome.transaction, transaction)

    def test_transaction_rejects_negative_or_inconsistent_balance(self) -> None:
        for before, after in ((10, -10), (25, 6), (10, 20)):
            with self.subTest(before=before, after=after):
                with self.assertRaises(ValueError):
                    PurchaseTransaction(
                        transaction_id=uuid4(),
                        item_id="starter.ribbon",
                        price=20,
                        balance_before=before,
                        balance_after=after,
                        purchased_at=_NOW,
                    )

    def test_denied_purchase_cannot_mutate_balance_or_contain_records(self) -> None:
        with self.assertRaises(ValueError):
            PurchaseOutcome(
                decision=PurchaseDecision.INSUFFICIENT_FUNDS,
                balance_before=10,
                balance_after=0,
            )

        with self.assertRaises(ValueError):
            PurchaseOutcome(
                decision=PurchaseDecision.ALREADY_OWNED,
                balance_before=20,
                balance_after=20,
                transaction=PurchaseTransaction(
                    transaction_id=uuid4(),
                    item_id="starter.ribbon",
                    price=0,
                    balance_before=20,
                    balance_after=20,
                    purchased_at=_NOW,
                ),
            )


class CosmeticLayerTest(unittest.TestCase):
    """Verify canonical-fidelity and trusted-path acceptance rules."""

    def test_accepts_known_states_directions_and_lossless_rendering(self) -> None:
        layer = CosmeticLayer(
            layer_id="starter.ribbon.layer",
            relative_asset_path="head/starter-ribbon/idle.png",
            compatible_states=frozenset({AnimationState.IDLE, AnimationState.WALKING}),
            compatible_directions=frozenset(FacingDirection),
            offset_y=-1,
            z_order=10,
        )

        self.assertTrue(layer.supports(AnimationState.IDLE, FacingDirection.LEFT))
        self.assertFalse(layer.supports(AnimationState.SLEEPING, FacingDirection.RIGHT))

    def test_rejects_unsafe_or_non_png_asset_paths(self) -> None:
        unsafe_paths = (
            "../standing/000.png",
            "/absolute/ribbon.png",
            "C:/private/ribbon.png",
            "head\\ribbon.png",
            "./head/ribbon.png",
            "head//ribbon.png",
            "head/ribbon.jpg",
        )

        for path in unsafe_paths:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    CosmeticLayer(
                        layer_id="starter.ribbon.layer",
                        relative_asset_path=path,
                        compatible_states=frozenset({AnimationState.IDLE}),
                        compatible_directions=frozenset({FacingDirection.RIGHT}),
                    )

    def test_rejects_unknown_compatibility_and_fidelity_changes(self) -> None:
        invalid_factories = (
            lambda: CosmeticLayer(
                "starter.ribbon.layer",
                "head/ribbon.png",
                frozenset(),
                frozenset({FacingDirection.RIGHT}),
            ),
            lambda: CosmeticLayer(
                "starter.ribbon.layer",
                "head/ribbon.png",
                frozenset({"idle"}),  # type: ignore[arg-type]
                frozenset({FacingDirection.RIGHT}),
            ),
            lambda: CosmeticLayer(
                "starter.ribbon.layer",
                "head/ribbon.png",
                frozenset({AnimationState.IDLE}),
                frozenset({FacingDirection.RIGHT}),
                canvas_width=101,
            ),
            lambda: CosmeticLayer(
                "starter.ribbon.layer",
                "head/ribbon.png",
                frozenset({AnimationState.IDLE}),
                frozenset({FacingDirection.RIGHT}),
                binary_alpha_required=False,
            ),
            lambda: CosmeticLayer(
                "starter.ribbon.layer",
                "head/ribbon.png",
                frozenset({AnimationState.IDLE}),
                frozenset({FacingDirection.RIGHT}),
                nearest_neighbor_required=False,
            ),
        )

        for factory in invalid_factories:
            with self.subTest(factory=factory):
                with self.assertRaises((TypeError, ValueError)):
                    factory()


if __name__ == "__main__":
    unittest.main()
