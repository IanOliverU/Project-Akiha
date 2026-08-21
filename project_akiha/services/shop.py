"""Application-facing trusted shop and ownership orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from project_akiha.core.appearance import AppearanceId
from project_akiha.core.events import EventBus, EventType
from project_akiha.core.pet import PetStateRecord
from project_akiha.core.shop import (
    CatalogLoadResult,
    CatalogQuery,
    PurchaseDecision,
    ShopBrowseResult,
    ShopInspectDecision,
    ShopInspectResult,
    ShopInventoryItemView,
    ShopItemView,
    ShopPurchaseResult,
    ShopRepository,
    browse_catalog,
)


class ShopClock(Protocol):
    """Clock dependency for deterministic purchase times."""

    def now(self) -> datetime:
        """Return one timezone-aware timestamp."""


class PetStateSnapshotService(Protocol):
    """Approved cache-reconciliation surface after economy mutations."""

    async def refresh_snapshot(self) -> PetStateRecord:
        """Reload the current durable pet-state record."""


class AppearanceReadService(Protocol):
    """Read-only appearance state needed by shop presentation and policy."""

    @property
    def current_appearance_id(self) -> AppearanceId:
        """Return the selected appearance."""

    def asset_available(self, appearance_id: AppearanceId) -> bool:
        """Return whether an approved complete manifest is available."""


class SystemShopClock:
    """Production UTC clock for shop operations."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class ShopService:
    """Expose typed shop operations without provider or dialogue integration."""

    def __init__(
        self,
        catalog_result: CatalogLoadResult,
        repository: ShopRepository,
        pet_state_service: PetStateSnapshotService,
        appearance_service: AppearanceReadService,
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
        self._appearance_service = appearance_service
        self._clock = clock
        self._event_bus = event_bus
        self._transaction_id_factory = transaction_id_factory
        self._lock = asyncio.Lock()

    async def browse(self, query: CatalogQuery | None = None) -> ShopBrowseResult:
        """Return a deterministic appearance catalog with ownership state."""
        if query is not None and not isinstance(query, CatalogQuery):
            raise TypeError("query must be a CatalogQuery value or None.")
        async with self._lock:
            inventory = await self._repository.list_inventory()
            state = await self._pet_state_service.refresh_snapshot()
            owned_ids = frozenset(item.item_id for item in inventory)
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
                        balance=progression.currency,
                        level=progression.level,
                    )
                    for item in items
                ),
            )

    async def inspect(self, item_id: str) -> ShopInspectResult:
        """Inspect one trusted product without exposing asset metadata."""
        _require_item_id(item_id)
        async with self._lock:
            item = self._catalog_result.catalog.item_by_id(item_id)
            if item is None:
                return ShopInspectResult(ShopInspectDecision.ITEM_NOT_FOUND, None)
            inventory = await self._repository.list_inventory()
            state = await self._pet_state_service.refresh_snapshot()
            return ShopInspectResult(
                ShopInspectDecision.FOUND,
                self._item_view(
                    item_id,
                    owned_ids=frozenset(owned.item_id for owned in inventory),
                    balance=state.state.progression.currency,
                    level=state.state.progression.level,
                ),
            )

    async def purchase(self, item_id: str) -> ShopPurchaseResult:
        """Purchase one exact trusted appearance through the atomic repository."""
        _require_item_id(item_id)
        async with self._lock:
            item = self._catalog_result.catalog.item_by_id(item_id)
            if item is None:
                return await self._denied_missing_purchase(item_id)
            if not self._appearance_service.asset_available(item.appearance_id):
                state = await self._pet_state_service.refresh_snapshot()
                balance = state.state.progression.currency
                return ShopPurchaseResult(
                    PurchaseDecision.ITEM_UNAVAILABLE,
                    item_id,
                    balance,
                    balance,
                )
            outcome = await self._repository.purchase(
                item,
                transaction_id=self._new_transaction_id(),
                purchased_at=self._current_time(),
            )
            if outcome.decision is PurchaseDecision.COMPLETED:
                await self._pet_state_service.refresh_snapshot()
                committed = outcome.transaction
                if committed is None:
                    raise RuntimeError("Completed purchase is missing its transaction.")
                result = ShopPurchaseResult(
                    outcome.decision,
                    item_id,
                    outcome.balance_before,
                    outcome.balance_after,
                    committed.transaction_id,
                )
                self._publish_purchase(result)
                return result
            return ShopPurchaseResult(
                outcome.decision,
                item_id,
                outcome.balance_before,
                outcome.balance_after,
            )

    async def inventory(self) -> tuple[ShopInventoryItemView, ...]:
        """Return durable ownership even when catalog metadata is later absent."""
        async with self._lock:
            inventory = await self._repository.list_inventory()
            selected = self._appearance_service.current_appearance_id
            return tuple(
                ShopInventoryItemView(
                    item_id=owned.item_id,
                    acquired_at=owned.acquired_at,
                    acquisition_source=owned.acquisition_source,
                    display_name=(catalog_item.display_name if catalog_item else None),
                    appearance_id=(
                        catalog_item.appearance_id if catalog_item else None
                    ),
                    availability=(catalog_item.availability if catalog_item else None),
                    asset_available=(
                        self._appearance_service.asset_available(
                            catalog_item.appearance_id
                        )
                        if catalog_item
                        else None
                    ),
                    selected=(
                        catalog_item is not None
                        and catalog_item.appearance_id is selected
                    ),
                    present_in_catalog=catalog_item is not None,
                )
                for owned in inventory
                for catalog_item in (
                    self._catalog_result.catalog.item_by_id(owned.item_id),
                )
            )

    def _item_view(
        self,
        item_id: str,
        *,
        owned_ids: frozenset[str],
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
            appearance_id=item.appearance_id,
            price=item.price,
            availability=item.availability,
            required_level=item.required_level,
            owned=item.item_id in owned_ids,
            selected=item.appearance_id
            is self._appearance_service.current_appearance_id,
            affordable=balance >= item.price,
            level_met=level >= item.required_level,
            asset_available=self._appearance_service.asset_available(
                item.appearance_id
            ),
        )

    async def _denied_missing_purchase(self, item_id: str) -> ShopPurchaseResult:
        state = await self._pet_state_service.refresh_snapshot()
        balance = state.state.progression.currency
        return ShopPurchaseResult(
            PurchaseDecision.ITEM_NOT_FOUND,
            item_id,
            balance,
            balance,
        )

    def _publish_purchase(self, result: ShopPurchaseResult) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(
                EventType.SHOP_PURCHASE_COMPLETED,
                {
                    "item_id": result.item_id,
                    "decision": result.decision.value,
                    "balance_after": result.balance_after,
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
