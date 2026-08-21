"""Selection orchestration for complete trusted Akiha appearances."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from project_akiha.core.appearance import (
    AppearanceAvailability,
    AppearanceId,
    AppearanceRegistry,
    AppearanceRepository,
    AppearanceSelection,
    AppearanceSelectionDecision,
    AppearanceSelectionOutcome,
    AppearanceView,
)
from project_akiha.core.events import EventBus, EventType
from project_akiha.core.shop import ShopRepository


class AppearanceClock(Protocol):
    """Clock dependency for deterministic selection timestamps."""

    def now(self) -> datetime:
        """Return one timezone-aware timestamp."""


class SystemAppearanceClock:
    """Production UTC appearance clock."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class AppearanceService:
    """Own availability, ownership, and selected whole-manifest state."""

    def __init__(
        self,
        registry: AppearanceRegistry,
        repository: AppearanceRepository,
        shop_repository: ShopRepository,
        clock: AppearanceClock,
        *,
        event_bus: EventBus | None = None,
    ) -> None:
        if not isinstance(registry, AppearanceRegistry):
            raise TypeError("registry must be an AppearanceRegistry value.")
        self._registry = registry
        self._repository = repository
        self._shop_repository = shop_repository
        self._clock = clock
        self._event_bus = event_bus
        self._selection: AppearanceSelection | None = None
        self._lock = asyncio.Lock()

    @property
    def current_appearance_id(self) -> AppearanceId:
        """Return the initialized selection without performing I/O."""
        if self._selection is None:
            raise RuntimeError("appearance service has not been initialized.")
        return self._selection.appearance_id

    @property
    def current_manifest_path(self) -> Path:
        """Return the selected trusted whole-set manifest."""
        path = self._registry.manifest_path(self.current_appearance_id)
        if path is None or not path.is_file():
            raise RuntimeError("selected appearance manifest is unavailable.")
        return path

    def asset_available(self, appearance_id: AppearanceId) -> bool:
        """Return whether one definition has an approved manifest on disk."""
        definition = self._registry.definition(appearance_id)
        if definition.availability is not AppearanceAvailability.AVAILABLE:
            return False
        path = self._registry.manifest_path(appearance_id)
        return path is not None and path.is_file()

    async def initialize(self) -> AppearanceSelection:
        """Load selection and repair stale unavailable ownership safely."""
        async with self._lock:
            selection = await self._repository.get_selection()
            if not await self._eligible(selection.appearance_id):
                selection = AppearanceSelection(
                    self._registry.default_appearance_id,
                    self._current_time(),
                )
                await self._repository.save_selection(selection)
            self._selection = selection
            return selection

    async def list_appearances(self) -> tuple[AppearanceView, ...]:
        """Return all three canonical appearances with bounded state."""
        async with self._lock:
            selection = self._require_selection()
            inventory = await self._shop_repository.list_inventory()
            owned_item_ids = frozenset(item.item_id for item in inventory)
            return tuple(
                AppearanceView(
                    appearance_id=definition.appearance_id,
                    display_name=definition.display_name,
                    availability=definition.availability,
                    owned=(
                        definition.required_item_id is None
                        or definition.required_item_id in owned_item_ids
                    ),
                    selected=definition.appearance_id is selection.appearance_id,
                )
                for definition in self._registry.definitions
            )

    async def select(
        self,
        appearance_id: AppearanceId,
    ) -> AppearanceSelectionOutcome:
        """Select one available owned complete appearance."""
        if not isinstance(appearance_id, AppearanceId):
            raise TypeError("appearance_id must be an AppearanceId value.")
        async with self._lock:
            current = self._require_selection()
            if not self.asset_available(appearance_id):
                return AppearanceSelectionOutcome(
                    AppearanceSelectionDecision.UNAVAILABLE,
                    current,
                    appearance_id,
                )
            definition = self._registry.definition(appearance_id)
            if definition.required_item_id is not None:
                owned = await self._shop_repository.get_inventory_item(
                    definition.required_item_id
                )
                if owned is None:
                    return AppearanceSelectionOutcome(
                        AppearanceSelectionDecision.NOT_OWNED,
                        current,
                        appearance_id,
                    )
            if appearance_id is current.appearance_id:
                return AppearanceSelectionOutcome(
                    AppearanceSelectionDecision.ALREADY_SELECTED,
                    current,
                    appearance_id,
                )
            selected = AppearanceSelection(appearance_id, self._current_time())
            self._selection = await self._repository.save_selection(selected)
            outcome = AppearanceSelectionOutcome(
                AppearanceSelectionDecision.SELECTED,
                self._selection,
                appearance_id,
            )
            self._publish(outcome)
            return outcome

    async def _eligible(self, appearance_id: AppearanceId) -> bool:
        if not self.asset_available(appearance_id):
            return False
        required_item_id = self._registry.definition(appearance_id).required_item_id
        return (
            required_item_id is None
            or await self._shop_repository.get_inventory_item(required_item_id)
            is not None
        )

    def _require_selection(self) -> AppearanceSelection:
        if self._selection is None:
            raise RuntimeError("appearance service has not been initialized.")
        return self._selection

    def _current_time(self) -> datetime:
        value = self._clock.now()
        if not isinstance(value, datetime):
            raise TypeError("AppearanceClock.now() must return a datetime.")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("AppearanceClock.now() must be timezone-aware.")
        return value.astimezone(UTC)

    def _publish(self, outcome: AppearanceSelectionOutcome) -> None:
        if self._event_bus is None:
            return
        self._event_bus.publish(
            EventType.APPEARANCE_CHANGED,
            {
                "appearance_id": outcome.selection.appearance_id.value,
                "decision": outcome.decision.value,
            },
        )
