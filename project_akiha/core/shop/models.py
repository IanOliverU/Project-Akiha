"""Framework-free shop, inventory, and cosmetic-layer contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from uuid import UUID

from project_akiha.core.state.animation import AnimationState

CANONICAL_COSMETIC_CANVAS_SIZE = (100, 100)
_MAX_IDENTIFIER_LENGTH = 64
_MAX_DISPLAY_NAME_LENGTH = 80
_MAX_LAYER_OFFSET = 100
_MAX_Z_ORDER = 100
_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class ShopItemCategory(StrEnum):
    """Initial closed catalog categories."""

    COSMETIC = "cosmetic"


class EquipmentSlot(StrEnum):
    """Single-occupancy visual equipment slots."""

    HEAD = "head"
    FACE = "face"
    NECK = "neck"
    ACCESSORY = "accessory"


class CatalogAvailability(StrEnum):
    """Whether an item may currently be shown or purchased."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    HIDDEN = "hidden"


class AcquisitionSource(StrEnum):
    """Trusted ways an inventory item may be granted."""

    STARTER = "starter"
    PURCHASE = "purchase"
    REWARD = "reward"
    MIGRATION = "migration"


class PurchaseDecision(StrEnum):
    """Closed purchase results used by the future economy service."""

    COMPLETED = "completed"
    ALREADY_OWNED = "already_owned"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    LEVEL_REQUIRED = "level_required"
    ITEM_UNAVAILABLE = "item_unavailable"


class FacingDirection(StrEnum):
    """Horizontal directions supported by one cosmetic layer."""

    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True, slots=True)
class CatalogItem:
    """One validated, non-stackable item from the trusted local catalog."""

    item_id: str
    display_name: str
    category: ShopItemCategory
    slot: EquipmentSlot
    price: int
    availability: CatalogAvailability
    required_level: int
    catalog_version: int
    preview_asset_id: str
    cosmetic_layer_id: str

    def __post_init__(self) -> None:
        _require_identifier(self.item_id, "item_id")
        _require_display_name(self.display_name)
        _require_enum(self.category, ShopItemCategory, "category")
        _require_enum(self.slot, EquipmentSlot, "slot")
        _require_nonnegative_int(self.price, "price")
        _require_enum(self.availability, CatalogAvailability, "availability")
        _require_positive_int(self.required_level, "required_level")
        _require_positive_int(self.catalog_version, "catalog_version")
        _require_identifier(self.preview_asset_id, "preview_asset_id")
        _require_identifier(self.cosmetic_layer_id, "cosmetic_layer_id")


@dataclass(frozen=True, slots=True)
class InventoryItem:
    """Durable ownership fact for one non-stackable catalog item."""

    item_id: str
    acquired_at: datetime
    acquisition_source: AcquisitionSource
    purchase_transaction_id: UUID | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.item_id, "item_id")
        _require_aware_datetime(self.acquired_at, "acquired_at")
        _require_enum(
            self.acquisition_source,
            AcquisitionSource,
            "acquisition_source",
        )
        if self.acquisition_source is AcquisitionSource.PURCHASE:
            if not isinstance(self.purchase_transaction_id, UUID):
                raise ValueError("purchased inventory requires a transaction ID.")
        elif self.purchase_transaction_id is not None:
            raise ValueError(
                "non-purchase inventory cannot reference a purchase transaction."
            )


@dataclass(frozen=True, slots=True)
class EquippedItem:
    """One owned item occupying one visual slot."""

    slot: EquipmentSlot
    item_id: str
    equipped_at: datetime

    def __post_init__(self) -> None:
        _require_enum(self.slot, EquipmentSlot, "slot")
        _require_identifier(self.item_id, "item_id")
        _require_aware_datetime(self.equipped_at, "equipped_at")


@dataclass(frozen=True, slots=True)
class EquipmentLoadout:
    """Immutable single-occupancy equipment loadout."""

    items: tuple[EquippedItem, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple) or any(
            not isinstance(item, EquippedItem) for item in self.items
        ):
            raise TypeError("items must be a tuple of EquippedItem values.")
        slots = tuple(item.slot for item in self.items)
        if len(slots) != len(set(slots)):
            raise ValueError("only one item may occupy an equipment slot.")
        item_ids = tuple(item.item_id for item in self.items)
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("an item cannot occupy multiple equipment slots.")

    def item_for(self, slot: EquipmentSlot) -> EquippedItem | None:
        """Return the item occupying one known slot, when present."""
        _require_enum(slot, EquipmentSlot, "slot")
        return next((item for item in self.items if item.slot is slot), None)


@dataclass(frozen=True, slots=True)
class PurchaseTransaction:
    """One completed atomic currency debit and ownership grant."""

    transaction_id: UUID
    item_id: str
    price: int
    balance_before: int
    balance_after: int
    purchased_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.transaction_id, UUID):
            raise TypeError("transaction_id must be a UUID.")
        _require_identifier(self.item_id, "item_id")
        _require_nonnegative_int(self.price, "price")
        _require_nonnegative_int(self.balance_before, "balance_before")
        _require_nonnegative_int(self.balance_after, "balance_after")
        if self.balance_before - self.price != self.balance_after:
            raise ValueError("purchase balances must reflect exactly one price debit.")
        _require_aware_datetime(self.purchased_at, "purchased_at")


@dataclass(frozen=True, slots=True)
class PurchaseOutcome:
    """Typed purchase result without provider-readable internal details."""

    decision: PurchaseDecision
    balance_before: int
    balance_after: int
    transaction: PurchaseTransaction | None = None
    inventory_item: InventoryItem | None = None

    def __post_init__(self) -> None:
        _require_enum(self.decision, PurchaseDecision, "decision")
        _require_nonnegative_int(self.balance_before, "balance_before")
        _require_nonnegative_int(self.balance_after, "balance_after")
        if self.decision is PurchaseDecision.COMPLETED:
            if not isinstance(self.transaction, PurchaseTransaction) or not isinstance(
                self.inventory_item, InventoryItem
            ):
                raise ValueError(
                    "a completed purchase requires a transaction and inventory item."
                )
            if self.transaction.item_id != self.inventory_item.item_id:
                raise ValueError("purchase transaction and inventory item must match.")
            if (
                self.inventory_item.purchase_transaction_id
                != self.transaction.transaction_id
            ):
                raise ValueError("inventory must reference its purchase transaction.")
            if (
                self.balance_before != self.transaction.balance_before
                or self.balance_after != self.transaction.balance_after
            ):
                raise ValueError(
                    "purchase outcome balances must match the transaction."
                )
        else:
            if self.transaction is not None or self.inventory_item is not None:
                raise ValueError("a denied purchase cannot contain committed records.")
            if self.balance_after != self.balance_before:
                raise ValueError("a denied purchase cannot change currency.")


@dataclass(frozen=True, slots=True)
class CosmeticLayer:
    """Approved lossless overlay metadata for the canonical 100x100 sprite."""

    layer_id: str
    relative_asset_path: str
    compatible_states: frozenset[AnimationState]
    compatible_directions: frozenset[FacingDirection]
    offset_x: int = 0
    offset_y: int = 0
    z_order: int = 0
    canvas_width: int = CANONICAL_COSMETIC_CANVAS_SIZE[0]
    canvas_height: int = CANONICAL_COSMETIC_CANVAS_SIZE[1]
    binary_alpha_required: bool = True
    nearest_neighbor_required: bool = True

    def __post_init__(self) -> None:
        _require_identifier(self.layer_id, "layer_id")
        _require_trusted_relative_path(self.relative_asset_path)
        _require_nonempty_enum_set(
            self.compatible_states,
            AnimationState,
            "compatible_states",
        )
        _require_nonempty_enum_set(
            self.compatible_directions,
            FacingDirection,
            "compatible_directions",
        )
        _require_bounded_int(self.offset_x, "offset_x", _MAX_LAYER_OFFSET)
        _require_bounded_int(self.offset_y, "offset_y", _MAX_LAYER_OFFSET)
        _require_bounded_int(self.z_order, "z_order", _MAX_Z_ORDER)
        if (self.canvas_width, self.canvas_height) != CANONICAL_COSMETIC_CANVAS_SIZE:
            raise ValueError("cosmetic layers must use the canonical 100x100 canvas.")
        if not isinstance(self.binary_alpha_required, bool):
            raise TypeError("binary_alpha_required must be a boolean.")
        if not self.binary_alpha_required:
            raise ValueError("cosmetic layers must preserve binary alpha.")
        if not isinstance(self.nearest_neighbor_required, bool):
            raise TypeError("nearest_neighbor_required must be a boolean.")
        if not self.nearest_neighbor_required:
            raise ValueError("cosmetic layers must require nearest-neighbor rendering.")

    def supports(
        self,
        state: AnimationState,
        direction: FacingDirection,
    ) -> bool:
        """Return whether this layer has an explicitly approved presentation."""
        _require_enum(state, AnimationState, "state")
        _require_enum(direction, FacingDirection, "direction")
        return (
            state in self.compatible_states and direction in self.compatible_directions
        )


def _require_identifier(value: object, label: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string.")
    if not 1 <= len(value) <= _MAX_IDENTIFIER_LENGTH:
        raise ValueError(f"{label} must be 1-{_MAX_IDENTIFIER_LENGTH} characters.")
    if _IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase stable identifier.")


def _require_display_name(value: object) -> None:
    if not isinstance(value, str):
        raise TypeError("display_name must be a string.")
    if value != value.strip() or not value:
        raise ValueError("display_name must be nonempty without edge whitespace.")
    if len(value) > _MAX_DISPLAY_NAME_LENGTH:
        raise ValueError(
            f"display_name cannot exceed {_MAX_DISPLAY_NAME_LENGTH} characters."
        )


def _require_trusted_relative_path(value: object) -> None:
    if not isinstance(value, str):
        raise TypeError("relative_asset_path must be a string.")
    if not value or "\\" in value or ":" in value:
        raise ValueError("relative_asset_path must use a trusted POSIX relative path.")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError("relative_asset_path cannot escape the cosmetic asset root.")
    if path.suffix.lower() != ".png":
        raise ValueError("cosmetic assets must be PNG files.")


def _require_nonempty_enum_set(
    value: object,
    enum_type: type[StrEnum],
    label: str,
) -> None:
    if not isinstance(value, frozenset) or not value:
        raise TypeError(f"{label} must be a nonempty frozenset.")
    if any(not isinstance(item, enum_type) for item in value):
        raise TypeError(f"{label} must contain only {enum_type.__name__} values.")


def _require_enum(value: object, enum_type: type[StrEnum], label: str) -> None:
    if not isinstance(value, enum_type):
        raise TypeError(f"{label} must be a {enum_type.__name__} value.")


def _require_nonnegative_int(value: object, label: str) -> None:
    if type(value) is not int:
        raise TypeError(f"{label} must be an integer.")
    if value < 0:
        raise ValueError(f"{label} cannot be negative.")


def _require_positive_int(value: object, label: str) -> None:
    if type(value) is not int:
        raise TypeError(f"{label} must be an integer.")
    if value <= 0:
        raise ValueError(f"{label} must be positive.")


def _require_bounded_int(value: object, label: str, absolute_limit: int) -> None:
    if type(value) is not int:
        raise TypeError(f"{label} must be an integer.")
    if not -absolute_limit <= value <= absolute_limit:
        raise ValueError(
            f"{label} must be between {-absolute_limit} and {absolute_limit}."
        )


def _require_aware_datetime(value: object, label: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{label} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware.")
