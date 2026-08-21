"""Tests for the compact shop and fixed-appearance surface."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import UTC, datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from project_akiha.core.appearance import (
    AppearanceAvailability,
    AppearanceId,
    AppearanceSelection,
    AppearanceSelectionDecision,
    AppearanceSelectionOutcome,
    AppearanceView,
)
from project_akiha.core.shop import (
    CatalogAvailability,
    CatalogLoadFailure,
    ShopBrowseResult,
    ShopItemCategory,
    ShopItemView,
)
from project_akiha.ui.shop_window import ShopWindow
from project_akiha.ui.shop_worker import (
    ShopUiSnapshot,
    ShopWorkerOperation,
    ShopWorkerResult,
)

_NOW = datetime(2026, 8, 21, 18, 0, tzinfo=UTC)


class ShopWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def tearDown(self) -> None:
        if hasattr(self, "_window"):
            self._window.close()

    def test_renders_catalog_and_three_fixed_appearances(self) -> None:
        self._window = ShopWindow()

        self._window.update_snapshot(_snapshot())

        self.assertEqual(self._window._summary_label.text(), "Level 3  |  90 currency")
        self.assertEqual(self._window._catalog_list.count(), 2)
        self.assertEqual(self._window._appearance_list.count(), 3)
        self.assertIn("Seifuku", self._window._appearance_list.item(0).text())

    def test_purchase_requires_confirmation_and_asset_availability(self) -> None:
        confirmations: list[str] = []
        self._window = ShopWindow(
            purchase_confirmation=lambda item: confirmations.append(item.item_id)
            or True
        )
        emitted: list[str] = []
        self._window.purchase_requested.connect(emitted.append)
        self._window.update_snapshot(_snapshot())
        _select_catalog_item(self._window, "appearance.dress")

        self._window._purchase_button.click()
        _select_catalog_item(self._window, "appearance.vermillion")

        self.assertEqual(confirmations, ["appearance.dress"])
        self.assertEqual(emitted, ["appearance.dress"])
        self.assertFalse(self._window._purchase_button.isEnabled())
        self.assertIn("animation set", self._window._item_status_label.text())

    def test_appearance_selection_emits_typed_identity(self) -> None:
        self._window = ShopWindow()
        emitted: list[AppearanceId] = []
        self._window.appearance_select_requested.connect(emitted.append)
        self._window.update_snapshot(_snapshot(dress_owned=True))
        self._window._tabs.setCurrentIndex(1)
        _select_appearance(self._window, AppearanceId.DRESS)

        self._window._select_appearance_button.click()

        self.assertEqual(emitted, [AppearanceId.DRESS])

    def test_results_and_failed_catalog_keep_appearance_selection_visible(self) -> None:
        self._window = ShopWindow()
        result = ShopWorkerResult(
            ShopWorkerOperation.SELECT_APPEARANCE,
            _snapshot(catalog_failure=CatalogLoadFailure.INVALID_SCHEMA),
            appearance=AppearanceSelectionOutcome(
                AppearanceSelectionDecision.SELECTED,
                AppearanceSelection(AppearanceId.DRESS, _NOW),
                AppearanceId.DRESS,
            ),
        )

        self._window.update_result(result)

        self.assertIn("Appearance selected", self._window._notice_label.text())
        self.assertEqual(self._window._appearance_list.count(), 3)

    def test_busy_state_and_type_guards(self) -> None:
        self._window = ShopWindow()
        self._window.update_snapshot(_snapshot())
        self._window.set_busy(True)

        self.assertFalse(self._window._refresh_button.isEnabled())
        self.assertFalse(self._window._category_filter.isEnabled())
        with self.assertRaises(TypeError):
            self._window.update_snapshot({})  # type: ignore[arg-type]


def _snapshot(
    *,
    dress_owned: bool = False,
    catalog_failure: CatalogLoadFailure | None = None,
) -> ShopUiSnapshot:
    items = (
        _shop_item(AppearanceId.DRESS, owned=dress_owned, asset_available=True),
        _shop_item(AppearanceId.VERMILLION, price=140, asset_available=False),
    )
    appearances = (
        AppearanceView(
            AppearanceId.SEIFUKU,
            "Akiha - Seifuku",
            AppearanceAvailability.AVAILABLE,
            True,
            True,
        ),
        AppearanceView(
            AppearanceId.DRESS,
            "Akiha - Dress",
            AppearanceAvailability.AVAILABLE,
            dress_owned,
            False,
        ),
        AppearanceView(
            AppearanceId.VERMILLION,
            "Akiha Vermillion",
            AppearanceAvailability.UNAVAILABLE,
            False,
            False,
        ),
    )
    return ShopUiSnapshot(
        browse=ShopBrowseResult(1, catalog_failure, 90, 3, items),
        inventory=(),
        appearances=appearances,
    )


def _shop_item(
    appearance_id: AppearanceId,
    *,
    price: int = 20,
    owned: bool = False,
    asset_available: bool,
) -> ShopItemView:
    return ShopItemView(
        item_id=f"appearance.{appearance_id.value}",
        display_name=f"Akiha - {appearance_id.value.title()}",
        category=ShopItemCategory.APPEARANCE,
        appearance_id=appearance_id,
        price=price,
        availability=CatalogAvailability.AVAILABLE,
        required_level=1,
        owned=owned,
        selected=False,
        affordable=True,
        level_met=True,
        asset_available=asset_available,
    )


def _select_catalog_item(window: ShopWindow, item_id: str) -> None:
    for index in range(window._catalog_list.count()):
        row = window._catalog_list.item(index)
        item = row.data(Qt.ItemDataRole.UserRole)
        if getattr(item, "item_id", None) == item_id:
            window._catalog_list.setCurrentItem(row)
            return
    raise AssertionError(f"catalog item not found: {item_id}")


def _select_appearance(window: ShopWindow, appearance_id: AppearanceId) -> None:
    for index in range(window._appearance_list.count()):
        row = window._appearance_list.item(index)
        appearance = row.data(Qt.ItemDataRole.UserRole)
        if getattr(appearance, "appearance_id", None) is appearance_id:
            window._appearance_list.setCurrentItem(row)
            return
    raise AssertionError(f"appearance not found: {appearance_id}")


if __name__ == "__main__":
    unittest.main()
