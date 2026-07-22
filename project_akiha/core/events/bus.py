"""Small in-process event bus for decoupled application modules."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from project_akiha.core.events.types import EventType

EventHandler = Callable[["Event"], None]


@dataclass(frozen=True, slots=True)
class Event:
    """A typed event with a lightweight payload."""

    event_type: EventType
    payload: dict[str, Any] = field(default_factory=dict)


class EventBus:
    """Publish events to handlers without coupling modules together."""

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Register a handler for a specific event type."""
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Remove a previously registered handler if present."""
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    def publish(
        self,
        event_type: EventType,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Send an event to all current subscribers."""
        event = Event(event_type=event_type, payload=payload or {})
        for handler in tuple(self._handlers[event_type]):
            handler(event)
