"""Strict trusted appearance-product catalog loading and browsing."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from project_akiha.core.appearance import AppearanceId
from project_akiha.core.shop.models import (
    CatalogAvailability,
    CatalogItem,
    ShopItemCategory,
)

SHOP_CATALOG_SCHEMA_VERSION = 2
_ROOT_KEYS = frozenset({"schema_version", "catalog_version", "items"})
_ITEM_KEYS = frozenset(
    {
        "item_id",
        "display_name",
        "category",
        "appearance_id",
        "price",
        "availability",
        "required_level",
    }
)


class CatalogError(ValueError):
    """Base error for an unreadable or invalid trusted catalog."""


class CatalogReadError(CatalogError):
    """Raised when the catalog file cannot be read."""


class CatalogDecodeError(CatalogError):
    """Raised when catalog TOML syntax is invalid."""


class CatalogValidationError(CatalogError):
    """Raised when decoded catalog data violates the closed schema."""


class CatalogLoadFailure(StrEnum):
    """Privacy-safe reason for using the empty catalog fallback."""

    MISSING = "missing"
    READ_FAILED = "read_failed"
    INVALID_TOML = "invalid_toml"
    INVALID_SCHEMA = "invalid_schema"


class CatalogOwnershipFilter(StrEnum):
    """Ownership filter for deterministic catalog browsing."""

    ALL = "all"
    OWNED = "owned"
    UNOWNED = "unowned"


class CatalogSort(StrEnum):
    """Stable catalog ordering modes."""

    NAME = "name"
    CATEGORY = "category"
    PRICE_LOW_TO_HIGH = "price_low_to_high"
    PRICE_HIGH_TO_LOW = "price_high_to_low"
    OWNERSHIP = "ownership"
    AVAILABILITY = "availability"


@dataclass(frozen=True, slots=True)
class ShopCatalog:
    """One immutable validated snapshot of trusted appearance products."""

    version: int
    items: tuple[CatalogItem, ...] = ()

    def __post_init__(self) -> None:
        _require_positive_int(self.version, "catalog version")
        _require_typed_tuple(self.items, CatalogItem, "catalog items")
        item_ids = tuple(item.item_id for item in self.items)
        appearance_ids = tuple(item.appearance_id for item in self.items)
        _reject_duplicates(item_ids, "item ID")
        _reject_duplicates(appearance_ids, "appearance ID")
        for item in self.items:
            if item.catalog_version != self.version:
                raise CatalogValidationError(
                    f"Item {item.item_id} does not match catalog version."
                )

    @classmethod
    def empty(cls, version: int = 1) -> ShopCatalog:
        """Return a valid catalog containing no purchasable content."""
        return cls(version=version)

    def item_by_id(self, item_id: str) -> CatalogItem | None:
        """Return one product by exact stable ID."""
        if not isinstance(item_id, str):
            raise TypeError("item_id must be a string.")
        return next((item for item in self.items if item.item_id == item_id), None)

    def item_for_appearance(self, appearance_id: AppearanceId) -> CatalogItem | None:
        """Return the product owning one non-default appearance."""
        if not isinstance(appearance_id, AppearanceId):
            raise TypeError("appearance_id must be an AppearanceId value.")
        return next(
            (item for item in self.items if item.appearance_id is appearance_id),
            None,
        )


@dataclass(frozen=True, slots=True)
class CatalogLoadResult:
    """Catalog load result with a bounded safe-fallback reason."""

    catalog: ShopCatalog
    failure: CatalogLoadFailure | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.catalog, ShopCatalog):
            raise TypeError("catalog must be a ShopCatalog value.")
        if self.failure is not None and not isinstance(
            self.failure, CatalogLoadFailure
        ):
            raise TypeError("failure must be a CatalogLoadFailure value or None.")

    @property
    def used_fallback(self) -> bool:
        """Return whether loading failed closed to the empty catalog."""
        return self.failure is not None


@dataclass(frozen=True, slots=True)
class CatalogQuery:
    """Typed filters and ordering for a local catalog snapshot."""

    category: ShopItemCategory | None = None
    availability: CatalogAvailability | None = None
    ownership: CatalogOwnershipFilter = CatalogOwnershipFilter.ALL
    sort: CatalogSort = CatalogSort.NAME

    def __post_init__(self) -> None:
        _require_optional_enum(self.category, ShopItemCategory, "category")
        _require_optional_enum(
            self.availability,
            CatalogAvailability,
            "availability",
        )
        _require_enum(self.ownership, CatalogOwnershipFilter, "ownership")
        _require_enum(self.sort, CatalogSort, "sort")


_EMPTY_OWNED_ITEM_IDS: frozenset[str] = frozenset()


def load_catalog(path: Path) -> ShopCatalog:
    """Load a trusted local catalog from disk."""
    if not isinstance(path, Path):
        raise TypeError("catalog path must be a Path value.")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise CatalogReadError("Unable to read the trusted shop catalog.") from error
    return parse_catalog_toml(text)


def load_catalog_or_empty(path: Path) -> CatalogLoadResult:
    """Load a trusted catalog, failing closed without leaking path details."""
    try:
        return CatalogLoadResult(catalog=load_catalog(path))
    except CatalogReadError as error:
        failure = (
            CatalogLoadFailure.MISSING
            if isinstance(error.__cause__, FileNotFoundError)
            else CatalogLoadFailure.READ_FAILED
        )
    except CatalogDecodeError:
        failure = CatalogLoadFailure.INVALID_TOML
    except CatalogValidationError:
        failure = CatalogLoadFailure.INVALID_SCHEMA
    return CatalogLoadResult(catalog=ShopCatalog.empty(), failure=failure)


def parse_catalog_toml(text: str) -> ShopCatalog:
    """Decode and validate catalog TOML without reading external resources."""
    if not isinstance(text, str):
        raise TypeError("catalog text must be a string.")
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise CatalogDecodeError("Invalid trusted shop catalog TOML.") from error
    return _parse_catalog_document(document)


def browse_catalog(
    catalog: ShopCatalog,
    *,
    query: CatalogQuery | None = None,
    owned_item_ids: frozenset[str] = _EMPTY_OWNED_ITEM_IDS,
) -> tuple[CatalogItem, ...]:
    """Filter and sort catalog items with deterministic tie breakers."""
    if not isinstance(catalog, ShopCatalog):
        raise TypeError("catalog must be a ShopCatalog value.")
    if query is None:
        query = CatalogQuery()
    if not isinstance(query, CatalogQuery):
        raise TypeError("query must be a CatalogQuery value.")
    if not isinstance(owned_item_ids, frozenset) or any(
        not isinstance(item_id, str) for item_id in owned_item_ids
    ):
        raise TypeError("owned_item_ids must be a frozenset of strings.")
    items = tuple(
        item for item in catalog.items if _matches_query(item, query, owned_item_ids)
    )
    return tuple(sorted(items, key=lambda item: _sort_key(item, query, owned_item_ids)))


def _parse_catalog_document(document: dict[str, Any]) -> ShopCatalog:
    _require_closed_table(document, _ROOT_KEYS, _ROOT_KEYS, "catalog")
    schema_version = document["schema_version"]
    if schema_version != SHOP_CATALOG_SCHEMA_VERSION or type(schema_version) is not int:
        raise CatalogValidationError(
            f"Unsupported shop catalog schema version: {schema_version!r}."
        )
    catalog_version = document["catalog_version"]
    _require_positive_int(catalog_version, "catalog_version")
    items_data = _require_table_array(document["items"], "items")
    items = tuple(
        _parse_item(item_data, index, catalog_version)
        for index, item_data in enumerate(items_data, start=1)
    )
    try:
        return ShopCatalog(version=catalog_version, items=items)
    except (TypeError, ValueError) as error:
        if isinstance(error, CatalogValidationError):
            raise
        raise CatalogValidationError("Catalog relationships are invalid.") from error


def _parse_item(
    data: dict[str, Any],
    index: int,
    catalog_version: int,
) -> CatalogItem:
    _require_closed_table(data, _ITEM_KEYS, _ITEM_KEYS, f"item {index}")
    try:
        return CatalogItem(
            item_id=data["item_id"],
            display_name=data["display_name"],
            category=ShopItemCategory(data["category"]),
            appearance_id=AppearanceId(data["appearance_id"]),
            price=data["price"],
            availability=CatalogAvailability(data["availability"]),
            required_level=data["required_level"],
            catalog_version=catalog_version,
        )
    except (TypeError, ValueError) as error:
        raise CatalogValidationError(f"Catalog item {index} is invalid.") from error


def _matches_query(
    item: CatalogItem,
    query: CatalogQuery,
    owned_item_ids: frozenset[str],
) -> bool:
    if query.category is not None and item.category is not query.category:
        return False
    if query.availability is not None:
        if item.availability is not query.availability:
            return False
    elif item.availability is CatalogAvailability.HIDDEN:
        return False
    is_owned = item.item_id in owned_item_ids
    if query.ownership is CatalogOwnershipFilter.OWNED and not is_owned:
        return False
    if query.ownership is CatalogOwnershipFilter.UNOWNED and is_owned:
        return False
    return True


def _sort_key(
    item: CatalogItem,
    query: CatalogQuery,
    owned_item_ids: frozenset[str],
) -> tuple[object, ...]:
    name_key = item.display_name.casefold()
    if query.sort is CatalogSort.CATEGORY:
        return (item.category.value, name_key, item.item_id)
    if query.sort is CatalogSort.PRICE_LOW_TO_HIGH:
        return (item.price, name_key, item.item_id)
    if query.sort is CatalogSort.PRICE_HIGH_TO_LOW:
        return (-item.price, name_key, item.item_id)
    if query.sort is CatalogSort.OWNERSHIP:
        return (0 if item.item_id in owned_item_ids else 1, name_key, item.item_id)
    if query.sort is CatalogSort.AVAILABILITY:
        ranks = {
            CatalogAvailability.AVAILABLE: 0,
            CatalogAvailability.UNAVAILABLE: 1,
            CatalogAvailability.HIDDEN: 2,
        }
        return (ranks[item.availability], name_key, item.item_id)
    return (name_key, item.item_id)


def _require_closed_table(
    value: object,
    required_keys: frozenset[str],
    allowed_keys: frozenset[str],
    label: str,
) -> None:
    if not isinstance(value, dict):
        raise CatalogValidationError(f"{label} must be a TOML table.")
    keys = frozenset(value)
    missing = required_keys - keys
    unknown = keys - allowed_keys
    if missing:
        raise CatalogValidationError(
            f"{label} is missing required field(s): {', '.join(sorted(missing))}."
        )
    if unknown:
        raise CatalogValidationError(
            f"{label} contains unknown field(s): {', '.join(sorted(unknown))}."
        )


def _require_table_array(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise CatalogValidationError(f"{label} must be an array of TOML tables.")
    return value


def _reject_duplicates(values: tuple[object, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise CatalogValidationError(f"Catalog contains a duplicate {label}.")


def _require_positive_int(value: object, label: str) -> None:
    if type(value) is not int:
        raise CatalogValidationError(f"{label} must be an integer.")
    if value <= 0:
        raise CatalogValidationError(f"{label} must be positive.")


def _require_typed_tuple(value: object, item_type: type, label: str) -> None:
    if not isinstance(value, tuple) or any(
        not isinstance(item, item_type) for item in value
    ):
        raise TypeError(f"{label} must be a tuple of {item_type.__name__} values.")


def _require_optional_enum(
    value: object,
    enum_type: type[StrEnum],
    label: str,
) -> None:
    if value is not None:
        _require_enum(value, enum_type, label)


def _require_enum(value: object, enum_type: type[StrEnum], label: str) -> None:
    if not isinstance(value, enum_type):
        raise TypeError(f"{label} must be a {enum_type.__name__} value.")
