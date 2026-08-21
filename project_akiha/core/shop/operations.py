"""Sanitized application-facing shop outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from project_akiha.core.appearance import AppearanceId
from project_akiha.core.shop.catalog import CatalogLoadFailure
from project_akiha.core.shop.models import (
    AcquisitionSource,
    CatalogAvailability,
    PurchaseDecision,
    ShopItemCategory,
)


class ShopInspectDecision(StrEnum):
    """Typed item lookup result."""

    FOUND = "found"
    ITEM_NOT_FOUND = "item_not_found"


@dataclass(frozen=True, slots=True)
class ShopItemView:
    """Catalog product state without manifest paths or raw asset metadata."""

    item_id: str
    display_name: str
    category: ShopItemCategory
    appearance_id: AppearanceId
    price: int
    availability: CatalogAvailability
    required_level: int
    owned: bool
    selected: bool
    affordable: bool
    level_met: bool
    asset_available: bool


@dataclass(frozen=True, slots=True)
class ShopBrowseResult:
    """One deterministic catalog snapshot for UI presentation."""

    catalog_version: int
    catalog_failure: CatalogLoadFailure | None
    balance: int
    level: int
    items: tuple[ShopItemView, ...]


@dataclass(frozen=True, slots=True)
class ShopInspectResult:
    """Typed inspect result that never exposes manifest paths."""

    decision: ShopInspectDecision
    item: ShopItemView | None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ShopInspectDecision):
            raise TypeError("decision must be a ShopInspectDecision value.")
        if self.decision is ShopInspectDecision.FOUND:
            if not isinstance(self.item, ShopItemView):
                raise ValueError("a found inspect result requires an item.")
        elif self.item is not None:
            raise ValueError("a missing inspect result cannot contain an item.")


@dataclass(frozen=True, slots=True)
class ShopInventoryItemView:
    """Durable ownership with optional current appearance metadata."""

    item_id: str
    acquired_at: datetime
    acquisition_source: AcquisitionSource
    display_name: str | None
    appearance_id: AppearanceId | None
    availability: CatalogAvailability | None
    asset_available: bool | None
    selected: bool
    present_in_catalog: bool


@dataclass(frozen=True, slots=True)
class ShopPurchaseResult:
    """Sanitized purchase result published after repository evaluation."""

    decision: PurchaseDecision
    item_id: str
    balance_before: int
    balance_after: int
    transaction_id: UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, PurchaseDecision):
            raise TypeError("decision must be a PurchaseDecision value.")
        if not isinstance(self.item_id, str) or not self.item_id:
            raise ValueError("item_id must be a nonempty string.")
        if type(self.balance_before) is not int or type(self.balance_after) is not int:
            raise TypeError("purchase balances must be integers.")
        if self.balance_before < 0 or self.balance_after < 0:
            raise ValueError("purchase balances cannot be negative.")
        if self.decision is PurchaseDecision.COMPLETED:
            if not isinstance(self.transaction_id, UUID):
                raise ValueError("a completed purchase requires a transaction ID.")
        elif self.transaction_id is not None:
            raise ValueError("a denied purchase cannot expose a transaction ID.")
