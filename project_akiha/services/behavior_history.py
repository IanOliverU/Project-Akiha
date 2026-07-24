"""Record behavior events from the application event bus."""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from project_akiha.core.behavior import BehaviorEvent
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType


class BehaviorHistoryRepository(Protocol):
    """Persistence boundary for behavior history."""

    async def record_event(
        self,
        event_type: str,
        payload: dict[str, object],
        kind: str | None = None,
    ) -> BehaviorEvent:
        """Persist one behavior event."""


class BehaviorHistoryRecorder:
    """Subscribe to behavior events and persist compact history rows."""

    _recorded_event_types = frozenset(
        {
            EventType.PROACTIVE_SUGGESTION_READY,
            EventType.PROACTIVE_SUGGESTION_DELIVERED,
        }
    )

    def __init__(
        self,
        event_bus: EventBus,
        repository: BehaviorHistoryRepository,
        logger: logging.Logger | None = None,
    ) -> None:
        self._repository = repository
        self._logger = logger or logging.getLogger("project_akiha.behavior_history")
        for event_type in self._recorded_event_types:
            event_bus.subscribe(event_type, self._handle_event)

    def _handle_event(self, event: Event) -> None:
        try:
            asyncio.run(
                self._repository.record_event(
                    event_type=event.event_type.value,
                    payload=dict(event.payload),
                    kind=_payload_kind(event.payload),
                )
            )
        except Exception:
            self._logger.exception(
                "Failed to record behavior event %s.",
                event.event_type.value,
            )


def _payload_kind(payload: dict[str, object]) -> str | None:
    kind = payload.get("kind")
    if isinstance(kind, str) and kind.strip():
        return kind
    return None
