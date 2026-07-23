"""Canonical event names used across Project Akiha."""

from __future__ import annotations

from enum import StrEnum


class EventType(StrEnum):
    """Known event types for the application event bus."""

    PET_DRAG_STARTED = "pet.drag_started"
    PET_DRAGGED = "pet.dragged"
    PET_DRAG_ENDED = "pet.drag_ended"
    PET_WALK_REQUESTED = "pet.walk_requested"
    PET_IDLE_REQUESTED = "pet.idle_requested"
    PET_SLEEP_REQUESTED = "pet.sleep_requested"
    PET_WAKE_REQUESTED = "pet.wake_requested"
    CHAT_OPEN_REQUESTED = "chat.open_requested"
    SETTINGS_OPEN_REQUESTED = "settings.open_requested"
    STATE_CHANGED = "state.changed"
    ERROR_OCCURRED = "error.occurred"
