"""Tests for the closed trusted appearance catalog."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from project_akiha.core.appearance import AppearanceId
from project_akiha.core.shop import (
    CatalogAvailability,
    CatalogDecodeError,
    CatalogLoadFailure,
    CatalogOwnershipFilter,
    CatalogQuery,
    CatalogSort,
    CatalogValidationError,
    ShopItemCategory,
    browse_catalog,
    load_catalog,
    load_catalog_or_empty,
    parse_catalog_toml,
)

_CATALOG = """
schema_version = 2
catalog_version = 3

[[items]]
item_id = "appearance.dress"
display_name = "Akiha - Dress"
category = "appearance"
appearance_id = "dress"
price = 100
availability = "available"
required_level = 2

[[items]]
item_id = "appearance.vermillion"
display_name = "Akiha Vermillion"
category = "appearance"
appearance_id = "vermillion"
price = 150
availability = "hidden"
required_level = 3
"""


class CatalogLoadingTest(unittest.TestCase):
    def test_bundled_catalog_is_valid_and_intentionally_empty(self) -> None:
        catalog = load_catalog(Path("project_akiha/config/shop_catalog.toml"))

        self.assertEqual(catalog.version, 1)
        self.assertEqual(catalog.items, ())

    def test_parses_closed_versioned_appearance_products(self) -> None:
        catalog = parse_catalog_toml(_CATALOG)

        self.assertEqual(catalog.version, 3)
        self.assertIs(catalog.items[0].category, ShopItemCategory.APPEARANCE)
        self.assertIs(catalog.items[0].appearance_id, AppearanceId.DRESS)
        vermillion = catalog.item_for_appearance(AppearanceId.VERMILLION)
        self.assertIsNotNone(vermillion)
        assert vermillion is not None
        self.assertEqual(vermillion.item_id, "appearance.vermillion")

    def test_rejects_wrong_schema_unknown_fields_and_duplicates(self) -> None:
        documents = (
            _CATALOG.replace("schema_version = 2", "schema_version = 1"),
            _CATALOG.replace("price = 100", 'price = 100\nslot = "head"', 1),
            _CATALOG.replace(
                'item_id = "appearance.vermillion"',
                'item_id = "appearance.dress"',
            ),
            _CATALOG.replace('appearance_id = "vermillion"', 'appearance_id = "dress"'),
        )
        for document in documents:
            with (
                self.subTest(document=document[-80:]),
                self.assertRaises(CatalogValidationError),
            ):
                parse_catalog_toml(document)

    def test_decode_and_file_failures_are_bounded(self) -> None:
        with self.assertRaises(CatalogDecodeError):
            parse_catalog_toml("[")
        with tempfile.TemporaryDirectory() as directory:
            result = load_catalog_or_empty(Path(directory) / "missing.toml")
        self.assertIs(result.failure, CatalogLoadFailure.MISSING)
        self.assertEqual(result.catalog.items, ())


class CatalogBrowsingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = parse_catalog_toml(_CATALOG)

    def test_default_hides_hidden_and_supports_typed_filters(self) -> None:
        default = browse_catalog(self.catalog)
        owned = browse_catalog(
            self.catalog,
            query=CatalogQuery(
                ownership=CatalogOwnershipFilter.OWNED,
                sort=CatalogSort.PRICE_HIGH_TO_LOW,
            ),
            owned_item_ids=frozenset({"appearance.dress"}),
        )
        hidden = browse_catalog(
            self.catalog,
            query=CatalogQuery(availability=CatalogAvailability.HIDDEN),
        )

        self.assertEqual([item.item_id for item in default], ["appearance.dress"])
        self.assertEqual([item.item_id for item in owned], ["appearance.dress"])
        self.assertEqual([item.item_id for item in hidden], ["appearance.vermillion"])

    def test_browse_rejects_untyped_inputs(self) -> None:
        with self.assertRaises(TypeError):
            browse_catalog(self.catalog, query="all")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            browse_catalog(self.catalog, owned_item_ids={"appearance.dress"})  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
