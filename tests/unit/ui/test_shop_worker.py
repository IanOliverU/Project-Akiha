"""Tests for typed non-blocking shop and appearance operations."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from uuid import UUID

from project_akiha.core.appearance import (
    AppearanceAvailability,
    AppearanceId,
    AppearanceSelection,
    AppearanceSelectionDecision,
    AppearanceSelectionOutcome,
    AppearanceView,
)
from project_akiha.core.shop import (
    CatalogQuery,
    PurchaseDecision,
    ShopBrowseResult,
    ShopPurchaseResult,
)
from project_akiha.ui.shop_worker import (
    ShopOperationThread,
    ShopUiSnapshot,
    ShopWorkerOperation,
)

_NOW = datetime(2026, 8, 21, 18, 0, tzinfo=UTC)


class ShopOperationThreadTest(unittest.TestCase):
    def test_refresh_reads_all_presentation_state_without_mutation(self) -> None:
        shop = _FakeShopService()
        appearance = _FakeAppearanceService()
        emitted: list[object] = []
        query = CatalogQuery()
        thread = ShopOperationThread(  # type: ignore[arg-type]
            shop,
            appearance,
            ShopWorkerOperation.REFRESH,
            query=query,
        )
        thread.completed.connect(emitted.append)

        thread.run()

        self.assertEqual(shop.mutations, [])
        self.assertEqual(shop.queries, [query])
        self.assertEqual(appearance.mutations, [])
        self.assertIsInstance(emitted[0].snapshot, ShopUiSnapshot)

    def test_purchase_and_selection_forward_only_typed_targets(self) -> None:
        shop = _FakeShopService()
        appearance = _FakeAppearanceService()
        purchase = ShopOperationThread(  # type: ignore[arg-type]
            shop,
            appearance,
            ShopWorkerOperation.PURCHASE,
            item_id="appearance.dress",
        )
        selection = ShopOperationThread(  # type: ignore[arg-type]
            shop,
            appearance,
            ShopWorkerOperation.SELECT_APPEARANCE,
            appearance_id=AppearanceId.DRESS,
        )

        purchase.run()
        selection.run()

        self.assertEqual(shop.mutations, [("purchase", "appearance.dress")])
        self.assertEqual(appearance.mutations, [AppearanceId.DRESS])

    def test_constructor_rejects_mismatched_arguments(self) -> None:
        shop = _FakeShopService()
        appearance = _FakeAppearanceService()
        with self.assertRaises(TypeError):
            ShopOperationThread(shop, appearance, "refresh")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            ShopOperationThread(
                shop,  # type: ignore[arg-type]
                appearance,  # type: ignore[arg-type]
                ShopWorkerOperation.PURCHASE,
            )
        with self.assertRaises(ValueError):
            ShopOperationThread(
                shop,  # type: ignore[arg-type]
                appearance,  # type: ignore[arg-type]
                ShopWorkerOperation.REFRESH,
                appearance_id=AppearanceId.DRESS,
            )


class _FakeShopService:
    def __init__(self) -> None:
        self.queries: list[CatalogQuery | None] = []
        self.mutations: list[tuple[str, str]] = []
        self.purchase_result = ShopPurchaseResult(
            PurchaseDecision.COMPLETED,
            "appearance.dress",
            100,
            80,
            UUID("11111111-1111-1111-1111-111111111111"),
        )

    async def browse(self, query: CatalogQuery | None = None) -> ShopBrowseResult:
        self.queries.append(query)
        return ShopBrowseResult(1, None, 80, 2, ())

    async def inventory(self) -> tuple[object, ...]:
        return ()

    async def purchase(self, item_id: str) -> ShopPurchaseResult:
        self.mutations.append(("purchase", item_id))
        return self.purchase_result


class _FakeAppearanceService:
    def __init__(self) -> None:
        self.mutations: list[AppearanceId] = []

    async def list_appearances(self) -> tuple[AppearanceView, ...]:
        return (
            AppearanceView(
                AppearanceId.SEIFUKU,
                "Akiha - Seifuku",
                AppearanceAvailability.AVAILABLE,
                True,
                True,
            ),
        )

    async def select(self, appearance_id: AppearanceId) -> AppearanceSelectionOutcome:
        self.mutations.append(appearance_id)
        selection = AppearanceSelection(appearance_id, _NOW)
        return AppearanceSelectionOutcome(
            AppearanceSelectionDecision.SELECTED,
            selection,
            appearance_id,
        )


if __name__ == "__main__":
    unittest.main()
