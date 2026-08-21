"""Tests for trusted appearance products and atomic purchases."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from uuid import UUID

from project_akiha.core.appearance import AppearanceId
from project_akiha.core.shop import (
    AcquisitionSource,
    CatalogAvailability,
    CatalogItem,
    InventoryItem,
    PurchaseDecision,
    PurchaseOutcome,
    PurchaseTransaction,
    ShopItemCategory,
)

_NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
_TRANSACTION_ID = UUID("11111111-1111-1111-1111-111111111111")


def _catalog_item(**changes: object) -> CatalogItem:
    values: dict[str, object] = {
        "item_id": "appearance.dress",
        "display_name": "Akiha - Dress",
        "category": ShopItemCategory.APPEARANCE,
        "appearance_id": AppearanceId.DRESS,
        "price": 20,
        "availability": CatalogAvailability.AVAILABLE,
        "required_level": 1,
        "catalog_version": 2,
    }
    values.update(changes)
    return CatalogItem(**values)  # type: ignore[arg-type]


class CatalogItemTest(unittest.TestCase):
    def test_accepts_complete_appearance_product(self) -> None:
        item = _catalog_item()

        self.assertIs(item.category, ShopItemCategory.APPEARANCE)
        self.assertIs(item.appearance_id, AppearanceId.DRESS)

    def test_rejects_default_appearance_and_invalid_values(self) -> None:
        invalid = (
            {"item_id": "Bad ID"},
            {"display_name": " Dress"},
            {"appearance_id": AppearanceId.SEIFUKU},
            {"price": -1},
            {"required_level": 0},
        )
        for changes in invalid:
            with (
                self.subTest(changes=changes),
                self.assertRaises((TypeError, ValueError)),
            ):
                _catalog_item(**changes)


class InventoryAndPurchaseTest(unittest.TestCase):
    def test_purchase_inventory_requires_transaction_provenance(self) -> None:
        purchased = InventoryItem(
            item_id="appearance.dress",
            acquired_at=_NOW,
            acquisition_source=AcquisitionSource.PURCHASE,
            purchase_transaction_id=_TRANSACTION_ID,
        )

        self.assertEqual(purchased.purchase_transaction_id, _TRANSACTION_ID)
        with self.assertRaises(ValueError):
            InventoryItem(
                item_id="appearance.dress",
                acquired_at=_NOW,
                acquisition_source=AcquisitionSource.PURCHASE,
            )
        with self.assertRaises(ValueError):
            InventoryItem(
                item_id="appearance.dress",
                acquired_at=_NOW,
                acquisition_source=AcquisitionSource.REWARD,
                purchase_transaction_id=_TRANSACTION_ID,
            )

    def test_completed_purchase_links_currency_and_inventory(self) -> None:
        transaction = PurchaseTransaction(
            transaction_id=_TRANSACTION_ID,
            item_id="appearance.dress",
            catalog_version=2,
            price=20,
            balance_before=100,
            balance_after=80,
            purchased_at=_NOW,
        )
        inventory = InventoryItem(
            item_id="appearance.dress",
            acquired_at=_NOW,
            acquisition_source=AcquisitionSource.PURCHASE,
            purchase_transaction_id=_TRANSACTION_ID,
        )

        outcome = PurchaseOutcome(
            PurchaseDecision.COMPLETED,
            100,
            80,
            transaction,
            inventory,
        )

        self.assertEqual(outcome.transaction, transaction)
        with self.assertRaises(ValueError):
            PurchaseOutcome(PurchaseDecision.COMPLETED, 100, 80)

    def test_denied_purchase_cannot_mutate_balance(self) -> None:
        with self.assertRaises(ValueError):
            PurchaseOutcome(PurchaseDecision.ITEM_UNAVAILABLE, 100, 80)


if __name__ == "__main__":
    unittest.main()
