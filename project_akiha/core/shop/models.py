"""Framework-free trusted shop, ownership, and economy contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from project_akiha.core.appearance import AppearanceId

_MAX_IDENTIFIER_LENGTH = 64
_MAX_DISPLAY_NAME_LENGTH = 80
_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class ShopItemCategory(StrEnum):
    """Closed Phase 10 product categories."""

    APPEARANCE = "appearance"


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
    """Closed atomic purchase results."""

    COMPLETED = "completed"
    ITEM_NOT_FOUND = "item_not_found"
    ALREADY_OWNED = "already_owned"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    LEVEL_REQUIRED = "level_required"
    ITEM_UNAVAILABLE = "item_unavailable"


@dataclass(frozen=True, slots=True)
class CatalogItem:
    """One validated non-stackable complete-appearance product."""

    item_id: str
    display_name: str
    category: ShopItemCategory
    appearance_id: AppearanceId
    price: int
    availability: CatalogAvailability
    required_level: int
    catalog_version: int

    def __post_init__(self) -> None:
        _require_identifier(self.item_id, "item_id")
        _require_display_name(self.display_name)
        _require_enum(self.category, ShopItemCategory, "category")
        _require_enum(self.appearance_id, AppearanceId, "appearance_id")
        _require_nonnegative_int(self.price, "price")
        _require_enum(self.availability, CatalogAvailability, "availability")
        _require_positive_int(self.required_level, "required_level")
        _require_positive_int(self.catalog_version, "catalog_version")
        if self.appearance_id is AppearanceId.SEIFUKU:
            raise ValueError("the canonical Seifuku appearance is not a shop product.")


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
        _require_enum(self.acquisition_source, AcquisitionSource, "acquisition_source")
        if self.acquisition_source is AcquisitionSource.PURCHASE:
            if not isinstance(self.purchase_transaction_id, UUID):
                raise ValueError("purchased inventory requires a transaction ID.")
        elif self.purchase_transaction_id is not None:
            raise ValueError(
                "non-purchase inventory cannot reference a purchase transaction."
            )


@dataclass(frozen=True, slots=True)
class PurchaseTransaction:
    """One completed atomic currency debit and ownership grant."""

    transaction_id: UUID
    item_id: str
    catalog_version: int
    price: int
    balance_before: int
    balance_after: int
    purchased_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.transaction_id, UUID):
            raise TypeError("transaction_id must be a UUID.")
        _require_identifier(self.item_id, "item_id")
        _require_positive_int(self.catalog_version, "catalog_version")
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


def _require_aware_datetime(value: object, label: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{label} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware.")
