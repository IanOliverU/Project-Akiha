"""Persistence boundary for the trusted shop and wardrobe."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from project_akiha.core.shop.models import (
    CatalogItem,
    EquipmentLoadout,
    EquipmentSlot,
    EquippedItem,
    InventoryItem,
    PurchaseOutcome,
    PurchaseTransaction,
)


class ShopStateUnavailableError(RuntimeError):
    """Raised when pet progression has not been initialized."""


class ShopIdempotencyConflictError(RuntimeError):
    """Raised when one transaction ID is reused for another item."""


class ShopRepository(Protocol):
    """Durable ownership, loadout, and atomic economy operations."""

    async def get_inventory_item(self, item_id: str) -> InventoryItem | None:
        """Return one durable ownership record when present."""

    async def list_inventory(self) -> tuple[InventoryItem, ...]:
        """Return all owned items in stable acquisition order."""

    async def get_loadout(self) -> EquipmentLoadout:
        """Return the current single-occupancy equipment loadout."""

    async def save_equipped_item(self, item: EquippedItem) -> EquipmentLoadout:
        """Persist one owned item in its selected slot."""

    async def remove_equipped_item(self, slot: EquipmentSlot) -> EquipmentLoadout:
        """Clear one equipment slot and return the resulting loadout."""

    async def get_transaction(
        self,
        transaction_id: UUID,
    ) -> PurchaseTransaction | None:
        """Return one completed purchase transaction when present."""

    async def list_transactions(self, limit: int) -> tuple[PurchaseTransaction, ...]:
        """Return recent completed purchases newest first."""

    async def purchase(
        self,
        item: CatalogItem,
        *,
        transaction_id: UUID,
        purchased_at: datetime,
    ) -> PurchaseOutcome:
        """Atomically debit pet currency and grant non-stackable ownership."""
