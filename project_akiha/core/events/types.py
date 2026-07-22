"""Canonical event names used across Project Akiha."""

from __future__ import annotations

from enum import StrEnum


class EventType(StrEnum):
    """Known event types for the application event bus."""

    PET_DRAG_STARTED = "pet.drag_started"
    PET_DRAGGED = "pet.dragged"
    PET_DRAG_ENDED = "pet.drag_ended"
    STATE_CHANGED = "state.changed"
    ERROR_OCCURRED = "error.occurred"

