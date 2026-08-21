"""Tests for the compact shop and wardrobe surface."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import UTC, datetime
from uuid import UUID

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from project_akiha.core.shop import (
    AcquisitionSource,
    CatalogAvailability,
    CatalogLoadFailure,
    EquipmentSlot,
    PurchaseDecision,
    ShopBrowseResult,
    ShopEquippedItemView,
    ShopInventoryItemView,
    ShopItemCategory,
    ShopItemView,
    ShopLoadoutView,
    ShopPurchaseResult,
)
from project_akiha.ui.shop_window import ShopWindow
from project_akiha.ui.shop_worker import (
    ShopUiSnapshot,
    ShopWorkerOperation,
    ShopWorkerResult,
)

_NOW = datetime(2026, 8, 21, 18, 0, tzinfo=UTC)


class ShopWindowTest(unittest.TestCase):
    """Verify dense presentation, confirmations, and typed control signals."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def tearDown(self) -> None:
        if hasattr(self, "_window"):
            self._window.close()

    def test_renders_balance_catalog_inventory_and_loadout(self) -> None:
        self._window = ShopWindow()

        self._window.update_snapshot(_snapshot())

        self.assertEqual(self._window._summary_label.text(), "Level 3  |  90 currency")
        self.assertEqual(self._window._catalog_list.count(), 4)
        self.assertEqual(self._window._inventory_list.count(), 1)
        self.assertEqual(
            self._window._loadout_labels[EquipmentSlot.HEAD].text(),
            "Red Ribbon",
        )
        self.assertTrue(self._window._unequip_buttons[EquipmentSlot.HEAD].isEnabled())

    def test_purchase_requires_confirmation_and_emits_exact_item_id(self) -> None:
        confirmations: list[str] = []

        def confirm(item: ShopItemView) -> bool:
            confirmations.append(item.item_id)
            return True

        self._window = ShopWindow(purchase_confirmation=confirm)
        emitted: list[str] = []
        self._window.purchase_requested.connect(emitted.append)
        self._window.update_snapshot(_snapshot())
        _select_catalog_item(self._window, "available.ribbon")

        self._window._purchase_button.click()

        self.assertEqual(confirmations, ["available.ribbon"])
        self.assertEqual(emitted, ["available.ribbon"])

    def test_unaffordable_and_incompatible_items_cannot_be_purchased(self) -> None:
        self._window = ShopWindow(purchase_confirmation=lambda item: True)
        self._window.update_snapshot(_snapshot())

        _select_catalog_item(self._window, "expensive.crown")
        self.assertFalse(self._window._purchase_button.isEnabled())
        self.assertIn("enough currency", self._window._item_status_label.text())

        _select_catalog_item(self._window, "broken.glasses")
        self.assertFalse(self._window._purchase_button.isEnabled())
        self.assertIn("visual layer", self._window._item_status_label.text())

    def test_search_filter_hides_nonmatching_rows(self) -> None:
        self._window = ShopWindow()
        self._window.update_snapshot(_snapshot())

        self._window._search_input.setText("crown")

        visible = [
            self._window._catalog_list.item(index).text()
            for index in range(self._window._catalog_list.count())
            if not self._window._catalog_list.item(index).isHidden()
        ]
        self.assertEqual(len(visible), 1)
        self.assertIn("Level Crown", visible[0])

    def test_available_view_builds_closed_unowned_available_query(self) -> None:
        self._window = ShopWindow()

        self._window._ownership_filter.setCurrentIndex(1)
        query = self._window.current_query()

        self.assertEqual(query.ownership.value, "unowned")
        self.assertIs(query.availability, CatalogAvailability.AVAILABLE)

    def test_wardrobe_emits_typed_equip_and_unequip_targets(self) -> None:
        self._window = ShopWindow()
        equipped: list[str] = []
        unequipped: list[EquipmentSlot] = []
        self._window.equip_requested.connect(equipped.append)
        self._window.unequip_requested.connect(unequipped.append)
        self._window.update_snapshot(_snapshot(inventory_equipped=False))

        self._window._equip_button.click()
        self._window.update_snapshot(_snapshot(inventory_equipped=True))
        self._window._unequip_buttons[EquipmentSlot.HEAD].click()

        self.assertEqual(equipped, ["owned.ribbon"])
        self.assertEqual(unequipped, [EquipmentSlot.HEAD])

    def test_operation_result_refreshes_state_and_renders_decision(self) -> None:
        self._window = ShopWindow()
        result = ShopWorkerResult(
            operation=ShopWorkerOperation.PURCHASE,
            snapshot=_snapshot(balance=70),
            purchase=ShopPurchaseResult(
                decision=PurchaseDecision.COMPLETED,
                item_id="available.ribbon",
                balance_before=90,
                balance_after=70,
                transaction_id=UUID("11111111-1111-1111-1111-111111111111"),
            ),
        )

        self._window.update_result(result)

        self.assertEqual(self._window._summary_label.text(), "Level 3  |  70 currency")
        self.assertIn("Purchase complete", self._window._notice_label.text())

    def test_empty_and_failed_catalog_preserve_wardrobe_state(self) -> None:
        self._window = ShopWindow()
        snapshot = _snapshot(catalog_failure=CatalogLoadFailure.INVALID_SCHEMA)
        snapshot = ShopUiSnapshot(
            browse=ShopBrowseResult(
                catalog_version=1,
                catalog_failure=CatalogLoadFailure.INVALID_SCHEMA,
                balance=snapshot.browse.balance,
                level=snapshot.browse.level,
                items=(),
            ),
            inventory=snapshot.inventory,
            loadout=snapshot.loadout,
        )

        self._window.update_snapshot(snapshot)

        self.assertIn("No catalog items", self._window._catalog_list.item(0).text())
        self.assertEqual(self._window._inventory_list.count(), 1)
        self.assertIn("could not be loaded", self._window._notice_label.text())
        self.assertEqual(self._window._notice_label.property("semantic"), "error")

    def test_busy_state_disables_mutation_and_filter_controls(self) -> None:
        self._window = ShopWindow()
        self._window.update_snapshot(_snapshot())
        _select_catalog_item(self._window, "available.ribbon")

        self._window.set_busy(True)

        self.assertFalse(self._window._refresh_button.isEnabled())
        self.assertFalse(self._window._category_filter.isEnabled())
        self.assertFalse(self._window._purchase_button.isEnabled())
        self.assertIn("Updating", self._window._notice_label.text())

    def test_rejects_untyped_snapshot_and_result(self) -> None:
        self._window = ShopWindow()
        with self.assertRaises(TypeError):
            self._window.update_snapshot({})  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            self._window.update_result({})  # type: ignore[arg-type]


def _snapshot(
    *,
    balance: int = 90,
    inventory_equipped: bool = True,
    catalog_failure: CatalogLoadFailure | None = None,
) -> ShopUiSnapshot:
    items = (
        _shop_item("available.ribbon", "Available Ribbon", price=20),
        _shop_item("expensive.crown", "Level Crown", price=120, affordable=False),
        _shop_item(
            "broken.glasses",
            "Black Glasses",
            price=30,
            visual_compatible=False,
        ),
        _shop_item("owned.ribbon", "Red Ribbon", price=20, owned=True),
    )
    inventory = (
        ShopInventoryItemView(
            item_id="owned.ribbon",
            acquired_at=_NOW,
            acquisition_source=AcquisitionSource.PURCHASE,
            display_name="Red Ribbon",
            slot=EquipmentSlot.HEAD,
            availability=CatalogAvailability.AVAILABLE,
            visual_compatible=True,
            equipped=inventory_equipped,
            present_in_catalog=True,
        ),
    )
    loadout = ShopLoadoutView(
        items=(
            (
                (
                    ShopEquippedItemView(
                        slot=EquipmentSlot.HEAD,
                        item_id="owned.ribbon",
                        display_name="Red Ribbon",
                        equipped_at=_NOW,
                        present_in_catalog=True,
                    )
                ),
            )
            if inventory_equipped
            else ()
        )
    )
    return ShopUiSnapshot(
        browse=ShopBrowseResult(
            catalog_version=1,
            catalog_failure=catalog_failure,
            balance=balance,
            level=3,
            items=items,
        ),
        inventory=inventory,
        loadout=loadout,
    )


def _shop_item(
    item_id: str,
    name: str,
    *,
    price: int,
    owned: bool = False,
    affordable: bool = True,
    visual_compatible: bool = True,
) -> ShopItemView:
    return ShopItemView(
        item_id=item_id,
        display_name=name,
        category=ShopItemCategory.COSMETIC,
        slot=EquipmentSlot.HEAD,
        price=price,
        availability=CatalogAvailability.AVAILABLE,
        required_level=1,
        owned=owned,
        equipped=False,
        affordable=affordable,
        level_met=True,
        visual_compatible=visual_compatible,
    )


def _select_catalog_item(window: ShopWindow, item_id: str) -> None:
    for index in range(window._catalog_list.count()):
        row = window._catalog_list.item(index)
        item = row.data(Qt.ItemDataRole.UserRole)
        if isinstance(item, ShopItemView) and item.item_id == item_id:
            window._catalog_list.setCurrentItem(row)
            return
    raise AssertionError(f"Catalog item not found: {item_id}")


if __name__ == "__main__":
    unittest.main()
