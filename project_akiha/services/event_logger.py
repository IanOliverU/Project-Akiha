"""Log high-level application events from the EventBus."""

from __future__ import annotations

import logging

from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType


class EventLogger:
    """Subscribe to app events and write useful diagnostics."""

    def __init__(
        self,
        event_bus: EventBus,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or logging.getLogger("project_akiha.events")
        for event_type in EventType:
            event_bus.subscribe(event_type, self._handle_event)

    def _handle_event(self, event: Event) -> None:
        if event.event_type == EventType.ERROR_OCCURRED:
            self._logger.error("%s %s", event.event_type.value, event.payload)
        elif event.event_type == EventType.PET_DRAGGED:
            self._logger.debug("%s %s", event.event_type.value, event.payload)
        else:
            self._logger.info("%s %s", event.event_type.value, event.payload)
