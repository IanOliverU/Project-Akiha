"""Behavior history records for proactive companion actions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class BehaviorEvent:
    """One persisted behavior event."""

    id: int
    event_type: str
    kind: str | None
    payload: Mapping[str, Any]
    created_at: str
