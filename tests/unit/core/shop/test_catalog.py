"""Tests for strict trusted catalog loading and deterministic browsing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from project_akiha.core.shop import (
    CatalogAvailability,
    CatalogDecodeError,
    CatalogLoadFailure,
    CatalogOwnershipFilter,
    CatalogQuery,
    CatalogSort,
    CatalogValidationError,
    EquipmentSlot,
    ShopCatalog,
    ShopItemCategory,
    browse_catalog,
    load_catalog,
    load_catalog_or_empty,
    parse_catalog_toml,
)
from project_akiha.core.state.animation import AnimationState

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_BUNDLED_CATALOG = _PROJECT_ROOT / "project_akiha" / "config" / "shop_catalog.toml"

_VALID_CATALOG = """
schema_version = 1
catalog_version = 3

[[layers]]
layer_id = "ribbon.red.layer"
asset_path = "head/ribbon-red/idle.png"
states = ["idle", "walking"]
directions = ["left", "right"]
offset_y = -1
z_order = 10

[[layers]]
layer_id = "glasses.black.layer"
asset_path = "face/glasses-black/idle.png"
states = ["idle"]
directions = ["left", "right"]
z_order = 20

[[layers]]
layer_id = "brooch.gold.layer"
asset_path = "accessory/brooch-gold/idle.png"
states = ["idle"]
directions = ["left", "right"]
z_order = 5

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
item_id = "glasses.black"
display_name = "Black Glasses"
category = "cosmetic"
slot = "face"
price = 40
availability = "unavailable"
required_level = 3
preview_asset_id = "glasses.black.layer"
cosmetic_layer_id = "glasses.black.layer"

[[items]]
item_id = "brooch.gold"
display_name = "Gold Brooch"
category = "cosmetic"
slot = "accessory"
price = 60
availability = "hidden"
required_level = 5
preview_asset_id = "brooch.gold.layer"
cosmetic_layer_id = "brooch.gold.layer"
"""


class CatalogLoadingTest(unittest.TestCase):
    """Verify strict schema parsing and fail-closed file loading."""

    def test_bundled_catalog_is_valid_and_intentionally_empty(self) -> None:
        catalog = load_catalog(_BUNDLED_CATALOG)

        self.assertEqual(catalog, ShopCatalog.empty())

    def test_parses_versioned_items_and_layers(self) -> None:
        catalog = parse_catalog_toml(_VALID_CATALOG)

        self.assertEqual(catalog.version, 3)
        self.assertEqual(len(catalog.items), 3)
        self.assertEqual(len(catalog.layers), 3)
        ribbon = catalog.item_by_id("ribbon.red")
        self.assertIsNotNone(ribbon)
        assert ribbon is not None
        self.assertIs(ribbon.category, ShopItemCategory.COSMETIC)
        self.assertIs(ribbon.slot, EquipmentSlot.HEAD)
        layer = catalog.layer_by_id(ribbon.cosmetic_layer_id)
        self.assertIsNotNone(layer)
        assert layer is not None
        self.assertIn(AnimationState.WALKING, layer.compatible_states)

    def test_rejects_wrong_schema_missing_and_unknown_fields(self) -> None:
        invalid_documents = (
            _VALID_CATALOG.replace("schema_version = 1", "schema_version = 2"),
            _VALID_CATALOG.replace("catalog_version = 3\n", ""),
            _VALID_CATALOG.replace(
                'display_name = "Red Ribbon"',
                'display_name = "Red Ribbon"\nremote_url = "https://example.com/item"',
            ),
        )

        for document in invalid_documents:
            with self.subTest(document=document[:40]):
                with self.assertRaises(CatalogValidationError):
                    parse_catalog_toml(document)

    def test_rejects_duplicate_item_layer_and_asset_path(self) -> None:
        duplicate_item = _VALID_CATALOG.replace(
            'item_id = "glasses.black"',
            'item_id = "ribbon.red"',
        )
        duplicate_layer = _VALID_CATALOG.replace(
            'layer_id = "glasses.black.layer"',
            'layer_id = "ribbon.red.layer"',
        )
        duplicate_path = _VALID_CATALOG.replace(
            'asset_path = "face/glasses-black/idle.png"',
            'asset_path = "head/ribbon-red/idle.png"',
        )

        for document in (duplicate_item, duplicate_layer, duplicate_path):
            with self.subTest(document=document[:40]):
                with self.assertRaises(CatalogValidationError):
                    parse_catalog_toml(document)

    def test_rejects_invalid_price_slot_and_asset_declarations(self) -> None:
        replacements = (
            ("price = 20", "price = -1"),
            ('slot = "head"', 'slot = "outfit"'),
            (
                'asset_path = "head/ribbon-red/idle.png"',
                'asset_path = "../standing/000.png"',
            ),
            ('states = ["idle", "walking"]', 'states = ["dancing"]'),
            ('directions = ["left", "right"]', 'directions = ["front"]'),
            ("canvas_width = 100", "canvas_width = 101"),
        )

        for original, replacement in replacements:
            document = _VALID_CATALOG.replace(original, replacement, 1)
            if original == "canvas_width = 100":
                document = _VALID_CATALOG.replace(
                    "z_order = 10",
                    "z_order = 10\ncanvas_width = 101",
                    1,
                )
            with self.subTest(replacement=replacement):
                with self.assertRaises(CatalogValidationError):
                    parse_catalog_toml(document)

    def test_rejects_unknown_or_mismatched_layer_references(self) -> None:
        unknown_cosmetic = _VALID_CATALOG.replace(
            'cosmetic_layer_id = "ribbon.red.layer"',
            'cosmetic_layer_id = "unknown.layer"',
            1,
        )
        unknown_preview = _VALID_CATALOG.replace(
            'preview_asset_id = "ribbon.red.layer"',
            'preview_asset_id = "unknown.layer"',
            1,
        )

        for document in (unknown_cosmetic, unknown_preview):
            with self.subTest(document=document[:40]):
                with self.assertRaises(CatalogValidationError):
                    parse_catalog_toml(document)

    def test_decode_error_is_distinct_from_schema_error(self) -> None:
        with self.assertRaises(CatalogDecodeError):
            parse_catalog_toml("schema_version = [")

    def test_missing_invalid_and_unreadable_files_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = load_catalog_or_empty(root / "missing.toml")
            invalid_toml_path = root / "invalid.toml"
            invalid_toml_path.write_text("schema_version = [", encoding="utf-8")
            invalid_toml = load_catalog_or_empty(invalid_toml_path)
            invalid_schema_path = root / "schema.toml"
            invalid_schema_path.write_text(
                "schema_version = 9\ncatalog_version = 1\nitems = []\nlayers = []\n",
                encoding="utf-8",
            )
            invalid_schema = load_catalog_or_empty(invalid_schema_path)
            unreadable = load_catalog_or_empty(root)

        expected = (
            (missing, CatalogLoadFailure.MISSING),
            (invalid_toml, CatalogLoadFailure.INVALID_TOML),
            (invalid_schema, CatalogLoadFailure.INVALID_SCHEMA),
            (unreadable, CatalogLoadFailure.READ_FAILED),
        )
        for result, failure in expected:
            with self.subTest(failure=failure):
                self.assertTrue(result.used_fallback)
                self.assertIs(result.failure, failure)
                self.assertEqual(result.catalog, ShopCatalog.empty())


class CatalogBrowsingTest(unittest.TestCase):
    """Verify filters, hidden-item behavior, and stable ordering."""

    def setUp(self) -> None:
        self.catalog = parse_catalog_toml(_VALID_CATALOG)
        self.owned = frozenset({"glasses.black"})

    def test_default_browse_hides_hidden_items_and_sorts_by_name(self) -> None:
        items = browse_catalog(self.catalog, owned_item_ids=self.owned)

        self.assertEqual(
            tuple(item.item_id for item in items),
            ("glasses.black", "ribbon.red"),
        )

    def test_filters_by_category_availability_and_ownership(self) -> None:
        query = CatalogQuery(
            category=ShopItemCategory.COSMETIC,
            availability=CatalogAvailability.UNAVAILABLE,
            ownership=CatalogOwnershipFilter.OWNED,
        )

        items = browse_catalog(self.catalog, query=query, owned_item_ids=self.owned)

        self.assertEqual(tuple(item.item_id for item in items), ("glasses.black",))

    def test_explicit_hidden_filter_can_inspect_hidden_entries(self) -> None:
        items = browse_catalog(
            self.catalog,
            query=CatalogQuery(availability=CatalogAvailability.HIDDEN),
        )

        self.assertEqual(tuple(item.item_id for item in items), ("brooch.gold",))

    def test_price_and_ownership_ordering_use_stable_tie_breakers(self) -> None:
        descending = browse_catalog(
            self.catalog,
            query=CatalogQuery(sort=CatalogSort.PRICE_HIGH_TO_LOW),
            owned_item_ids=self.owned,
        )
        ownership = browse_catalog(
            self.catalog,
            query=CatalogQuery(sort=CatalogSort.OWNERSHIP),
            owned_item_ids=self.owned,
        )

        self.assertEqual(
            tuple(item.item_id for item in descending),
            ("glasses.black", "ribbon.red"),
        )
        self.assertEqual(
            tuple(item.item_id for item in ownership),
            ("glasses.black", "ribbon.red"),
        )

    def test_browse_rejects_untyped_query_and_ownership(self) -> None:
        with self.assertRaises(TypeError):
            browse_catalog(self.catalog, query="price")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            browse_catalog(
                self.catalog,
                owned_item_ids={"ribbon.red"},  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
