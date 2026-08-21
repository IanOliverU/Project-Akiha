"""Application-facing shop, inventory, and wardrobe orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from project_akiha.core.events import EventBus, EventType
from project_akiha.core.pet import PetStateRecord
from project_akiha.core.shop import (
    CatalogLoadResult,
    CatalogQuery,
    EquipmentDecision,
    EquipmentLoadout,
    EquipmentOutcome,
    EquipmentSlot,
    EquippedItem,
    FacingDirection,
    PurchaseDecision,
    ShopBrowseResult,
    ShopEquippedItemView,
    ShopInspectDecision,
    ShopInspectResult,
    ShopInventoryItemView,
    ShopItemView,
    ShopLoadoutView,
    ShopPurchaseResult,
    ShopRepository,
    browse_catalog,
)
from project_akiha.core.state.animation import AnimationState


class ShopClock(Protocol):
    """Clock dependency for deterministic purchase and equipment times."""

    def now(self) -> datetime:
        """Return one timezone-aware timestamp."""


class PetStateSnapshotService(Protocol):
    """Approved cache-reconciliation surface after economy mutations."""

    async def refresh_snapshot(self) -> PetStateRecord:
        """Reload the current durable pet-state record."""


class SystemShopClock:
    """Production UTC clock for shop operations."""

    def now(self) -> datetime:
        """Return the current UTC time."""
        return datetime.now(UTC)


class ShopService:
    """Expose typed shop operations without provider or dialogue integration."""

    def __init__(
        self,
        catalog_result: CatalogLoadResult,
        repository: ShopRepository,
        pet_state_service: PetStateSnapshotService,
        clock: ShopClock,
        *,
        event_bus: EventBus | None = None,
        transaction_id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        if not isinstance(catalog_result, CatalogLoadResult):
            raise TypeError("catalog_result must be a CatalogLoadResult value.")
        if event_bus is not None and not isinstance(event_bus, EventBus):
            raise TypeError("event_bus must be an EventBus value or None.")
        if not callable(transaction_id_factory):
            raise TypeError("transaction_id_factory must be callable.")
        self._catalog_result = catalog_result
        self._repository = repository
        self._pet_state_service = pet_state_service
        self._clock = clock
        self._event_bus = event_bus
        self._transaction_id_factory = transaction_id_factory
        self._lock = asyncio.Lock()

    async def browse(self, query: CatalogQuery | None = None) -> ShopBrowseResult:
        """Return a deterministic catalog snapshot with ownership state."""
        if query is not None and not isinstance(query, CatalogQuery):
            raise TypeError("query must be a CatalogQuery value or None.")
        async with self._lock:
            inventory = await self._repository.list_inventory()
            loadout = await self._repository.get_loadout()
            state = await self._pet_state_service.refresh_snapshot()
            owned_ids = frozenset(item.item_id for item in inventory)
            equipped_ids = frozenset(item.item_id for item in loadout.items)
            items = browse_catalog(
                self._catalog_result.catalog,
                query=query,
                owned_item_ids=owned_ids,
            )
            progression = state.state.progression
            return ShopBrowseResult(
                catalog_version=self._catalog_result.catalog.version,
                catalog_failure=self._catalog_result.failure,
                balance=progression.currency,
                level=progression.level,
                items=tuple(
                    self._item_view(
                        item.item_id,
                        owned_ids=owned_ids,
                        equipped_ids=equipped_ids,
                        balance=progression.currency,
                        level=progression.level,
                    )
                    for item in items
                ),
            )

    async def inspect(self, item_id: str) -> ShopInspectResult:
        """Inspect one trusted catalog item without exposing asset metadata."""
        _require_item_id(item_id)
        async with self._lock:
            item = self._catalog_result.catalog.item_by_id(item_id)
            if item is None:
                return ShopInspectResult(
                    decision=ShopInspectDecision.ITEM_NOT_FOUND,
                    item=None,
                )
            inventory = await self._repository.list_inventory()
            loadout = await self._repository.get_loadout()
            state = await self._pet_state_service.refresh_snapshot()
            return ShopInspectResult(
                decision=ShopInspectDecision.FOUND,
                item=self._item_view(
                    item_id,
                    owned_ids=frozenset(owned.item_id for owned in inventory),
                    equipped_ids=frozenset(
                        equipped.item_id for equipped in loadout.items
                    ),
                    balance=state.state.progression.currency,
                    level=state.state.progression.level,
                ),
            )

    async def purchase(self, item_id: str) -> ShopPurchaseResult:
        """Purchase one exact trusted catalog item through the atomic repository."""
        _require_item_id(item_id)
        async with self._lock:
            item = self._catalog_result.catalog.item_by_id(item_id)
            if item is None:
                state = await self._pet_state_service.refresh_snapshot()
                balance = state.state.progression.currency
                return ShopPurchaseResult(
                    decision=PurchaseDecision.ITEM_NOT_FOUND,
                    item_id=item_id,
                    balance_before=balance,
                    balance_after=balance,
                )

            transaction_id = self._new_transaction_id()
            outcome = await self._repository.purchase(
                item,
                transaction_id=transaction_id,
                purchased_at=self._current_time(),
            )
            if outcome.decision is PurchaseDecision.COMPLETED:
                await self._pet_state_service.refresh_snapshot()
                committed = outcome.transaction
                if committed is None:
                    raise RuntimeError("Completed purchase is missing its transaction.")
                result = ShopPurchaseResult(
                    decision=outcome.decision,
                    item_id=item_id,
                    balance_before=outcome.balance_before,
                    balance_after=outcome.balance_after,
                    transaction_id=committed.transaction_id,
                )
                self._publish_purchase(result)
                return result
            return ShopPurchaseResult(
                decision=outcome.decision,
                item_id=item_id,
                balance_before=outcome.balance_before,
                balance_after=outcome.balance_after,
            )

    async def inventory(self) -> tuple[ShopInventoryItemView, ...]:
        """Return durable ownership even when a catalog entry is later absent."""
        async with self._lock:
            inventory = await self._repository.list_inventory()
            loadout = await self._repository.get_loadout()
            equipped_ids = frozenset(item.item_id for item in loadout.items)
            return tuple(
                ShopInventoryItemView(
                    item_id=owned.item_id,
                    acquired_at=owned.acquired_at,
                    acquisition_source=owned.acquisition_source,
                    display_name=(catalog_item.display_name if catalog_item else None),
                    slot=(catalog_item.slot if catalog_item else None),
                    availability=(catalog_item.availability if catalog_item else None),
                    visual_compatible=(
                        self._visual_compatible(owned.item_id) if catalog_item else None
                    ),
                    equipped=owned.item_id in equipped_ids,
                    present_in_catalog=catalog_item is not None,
                )
                for owned in inventory
                for catalog_item in (
                    self._catalog_result.catalog.item_by_id(owned.item_id),
                )
            )

    async def loadout(self) -> ShopLoadoutView:
        """Return current equipment without asset paths."""
        async with self._lock:
            return self._loadout_view(await self._repository.get_loadout())

    async def equip(self, item_id: str) -> EquipmentOutcome:
        """Equip one owned compatible item in its catalog-declared slot."""
        _require_item_id(item_id)
        async with self._lock:
            current = await self._repository.get_loadout()
            item = self._catalog_result.catalog.item_by_id(item_id)
            if item is None:
                return EquipmentOutcome(
                    decision=EquipmentDecision.ITEM_NOT_FOUND,
                    loadout=self._loadout_view(current),
                    item_id=item_id,
                )
            if await self._repository.get_inventory_item(item_id) is None:
                return EquipmentOutcome(
                    decision=EquipmentDecision.NOT_OWNED,
                    loadout=self._loadout_view(current),
                    slot=item.slot,
                    item_id=item_id,
                )
            if not self._visual_compatible(item_id):
                return EquipmentOutcome(
                    decision=EquipmentDecision.VISUAL_INCOMPATIBLE,
                    loadout=self._loadout_view(current),
                    slot=item.slot,
                    item_id=item_id,
                )
            occupying = current.item_for(item.slot)
            if occupying is not None and occupying.item_id == item_id:
                return EquipmentOutcome(
                    decision=EquipmentDecision.ALREADY_EQUIPPED,
                    loadout=self._loadout_view(current),
                    slot=item.slot,
                    item_id=item_id,
                )

            committed = await self._repository.save_equipped_item(
                EquippedItem(
                    slot=item.slot,
                    item_id=item_id,
                    equipped_at=self._current_time(),
                )
            )
            result = EquipmentOutcome(
                decision=EquipmentDecision.EQUIPPED,
                loadout=self._loadout_view(committed),
                slot=item.slot,
                item_id=item_id,
            )
            self._publish_equipment(result)
            return result

    async def unequip(self, slot: EquipmentSlot) -> EquipmentOutcome:
        """Clear one slot without deleting durable ownership."""
        if not isinstance(slot, EquipmentSlot):
            raise TypeError("slot must be an EquipmentSlot value.")
        async with self._lock:
            current = await self._repository.get_loadout()
            occupying = current.item_for(slot)
            if occupying is None:
                return EquipmentOutcome(
                    decision=EquipmentDecision.EMPTY_SLOT,
                    loadout=self._loadout_view(current),
                    slot=slot,
                )
            committed = await self._repository.remove_equipped_item(slot)
            result = EquipmentOutcome(
                decision=EquipmentDecision.UNEQUIPPED,
                loadout=self._loadout_view(committed),
                slot=slot,
                item_id=occupying.item_id,
            )
            self._publish_equipment(result)
            return result

    def _item_view(
        self,
        item_id: str,
        *,
        owned_ids: frozenset[str],
        equipped_ids: frozenset[str],
        balance: int,
        level: int,
    ) -> ShopItemView:
        item = self._catalog_result.catalog.item_by_id(item_id)
        if item is None:
            raise RuntimeError("Catalog item disappeared from an immutable snapshot.")
        return ShopItemView(
            item_id=item.item_id,
            display_name=item.display_name,
            category=item.category,
            slot=item.slot,
            price=item.price,
            availability=item.availability,
            required_level=item.required_level,
            owned=item.item_id in owned_ids,
            equipped=item.item_id in equipped_ids,
            affordable=balance >= item.price,
            level_met=level >= item.required_level,
            visual_compatible=self._visual_compatible(item.item_id),
        )

    def _visual_compatible(self, item_id: str) -> bool:
        item = self._catalog_result.catalog.item_by_id(item_id)
        if item is None:
            return False
        layer = self._catalog_result.catalog.layer_by_id(item.cosmetic_layer_id)
        if layer is None:
            return False
        return all(
            layer.supports(AnimationState.IDLE, direction)
            for direction in FacingDirection
        )

    def _loadout_view(self, loadout: EquipmentLoadout) -> ShopLoadoutView:
        return ShopLoadoutView(
            items=tuple(
                ShopEquippedItemView(
                    slot=equipped.slot,
                    item_id=equipped.item_id,
                    display_name=(item.display_name if item else None),
                    equipped_at=equipped.equipped_at,
                    present_in_catalog=item is not None,
                )
                for equipped in loadout.items
                for item in (self._catalog_result.catalog.item_by_id(equipped.item_id),)
            )
        )

    def _publish_purchase(self, result: ShopPurchaseResult) -> None:
        if self._event_bus is None:
            return
        self._event_bus.publish(
            EventType.SHOP_PURCHASE_COMPLETED,
            {
                "item_id": result.item_id,
                "decision": result.decision.value,
                "balance_after": result.balance_after,
            },
        )

    def _publish_equipment(self, result: EquipmentOutcome) -> None:
        if self._event_bus is None:
            return
        self._event_bus.publish(
            EventType.SHOP_EQUIPMENT_CHANGED,
            {
                "item_id": result.item_id,
                "slot": result.slot.value if result.slot is not None else None,
                "decision": result.decision.value,
            },
        )

    def _new_transaction_id(self) -> UUID:
        value = self._transaction_id_factory()
        if not isinstance(value, UUID):
            raise TypeError("transaction_id_factory must return a UUID.")
        return value

    def _current_time(self) -> datetime:
        value = self._clock.now()
        if not isinstance(value, datetime):
            raise TypeError("ShopClock.now() must return a datetime.")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("ShopClock.now() must return a timezone-aware datetime.")
        return value.astimezone(UTC)


def _require_item_id(item_id: object) -> None:
    if not isinstance(item_id, str):
        raise TypeError("item_id must be a string.")
    if not item_id:
        raise ValueError("item_id cannot be empty.")
