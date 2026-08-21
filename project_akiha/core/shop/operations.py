"""Sanitized application-facing shop and wardrobe outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from project_akiha.core.shop.catalog import CatalogLoadFailure
from project_akiha.core.shop.models import (
    AcquisitionSource,
    CatalogAvailability,
    EquipmentSlot,
    PurchaseDecision,
    ShopItemCategory,
)


class ShopInspectDecision(StrEnum):
    """Typed item lookup result."""

    FOUND = "found"
    ITEM_NOT_FOUND = "item_not_found"


class EquipmentDecision(StrEnum):
    """Closed results for equip and unequip operations."""

    EQUIPPED = "equipped"
    UNEQUIPPED = "unequipped"
    ALREADY_EQUIPPED = "already_equipped"
    EMPTY_SLOT = "empty_slot"
    ITEM_NOT_FOUND = "item_not_found"
    NOT_OWNED = "not_owned"
    VISUAL_INCOMPATIBLE = "visual_incompatible"


@dataclass(frozen=True, slots=True)
class ShopItemView:
    """Catalog item state without paths or raw visual metadata."""

    item_id: str
    display_name: str
    category: ShopItemCategory
    slot: EquipmentSlot
    price: int
    availability: CatalogAvailability
    required_level: int
    owned: bool
    equipped: bool
    affordable: bool
    level_met: bool
    visual_compatible: bool


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
    """Typed inspect result that never exposes layer paths."""

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
    """Durable ownership state with optional current catalog metadata."""

    item_id: str
    acquired_at: datetime
    acquisition_source: AcquisitionSource
    display_name: str | None
    slot: EquipmentSlot | None
    equipped: bool
    present_in_catalog: bool


@dataclass(frozen=True, slots=True)
class ShopEquippedItemView:
    """One equipment slot without visual asset paths."""

    slot: EquipmentSlot
    item_id: str
    display_name: str | None
    equipped_at: datetime
    present_in_catalog: bool


@dataclass(frozen=True, slots=True)
class ShopLoadoutView:
    """Sanitized ordered equipment snapshot."""

    items: tuple[ShopEquippedItemView, ...] = ()

    def item_for(self, slot: EquipmentSlot) -> ShopEquippedItemView | None:
        """Return one visible slot entry when present."""
        if not isinstance(slot, EquipmentSlot):
            raise TypeError("slot must be an EquipmentSlot value.")
        return next((item for item in self.items if item.slot is slot), None)


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


@dataclass(frozen=True, slots=True)
class EquipmentOutcome:
    """Sanitized result and committed loadout for one equipment request."""

    decision: EquipmentDecision
    loadout: ShopLoadoutView
    slot: EquipmentSlot | None = None
    item_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, EquipmentDecision):
            raise TypeError("decision must be an EquipmentDecision value.")
        if not isinstance(self.loadout, ShopLoadoutView):
            raise TypeError("loadout must be a ShopLoadoutView value.")
        if self.slot is not None and not isinstance(self.slot, EquipmentSlot):
            raise TypeError("slot must be an EquipmentSlot value or None.")
        if self.item_id is not None and (
            not isinstance(self.item_id, str) or not self.item_id
        ):
            raise ValueError("item_id must be a nonempty string or None.")
