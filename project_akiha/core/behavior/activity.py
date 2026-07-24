"""User activity state tracking for proactive companion behavior."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class ActivityState(StrEnum):
    """Coarse user availability inferred from recent activity."""

    ACTIVE = "active"
    IDLE = "idle"
    AWAY = "away"


@dataclass(frozen=True, slots=True)
class ActivitySnapshot:
    """A point-in-time summary of recent user activity."""

    state: ActivityState
    idle_seconds: int
    last_activity_at: datetime
    source: str


class ActivityTracker:
    """Track recent app-local activity and infer active/idle/away state."""

    def __init__(
        self,
        *,
        idle_after_seconds: int,
        away_after_seconds: int,
        initial_time: datetime | None = None,
        source: str = "startup",
    ) -> None:
        self._validate_thresholds(idle_after_seconds, away_after_seconds)
        self._idle_after_seconds = idle_after_seconds
        self._away_after_seconds = away_after_seconds
        self._last_activity_at = initial_time or _now()
        self._source = source

    def update_thresholds(
        self,
        *,
        idle_after_seconds: int,
        away_after_seconds: int,
    ) -> None:
        """Update idle/away thresholds without resetting observed activity."""
        self._validate_thresholds(idle_after_seconds, away_after_seconds)
        self._idle_after_seconds = idle_after_seconds
        self._away_after_seconds = away_after_seconds

    def record_activity(
        self,
        source: str,
        occurred_at: datetime | None = None,
    ) -> ActivitySnapshot:
        """Record user activity and return the resulting active snapshot."""
        self._last_activity_at = occurred_at or _now()
        self._source = source
        return self.snapshot(self._last_activity_at)

    def snapshot(self, now: datetime | None = None) -> ActivitySnapshot:
        """Return the current inferred user activity state."""
        current_time = now or _now()
        idle_seconds = max(
            0,
            round((current_time - self._last_activity_at).total_seconds()),
        )
        return ActivitySnapshot(
            state=self._state_for(idle_seconds),
            idle_seconds=idle_seconds,
            last_activity_at=self._last_activity_at,
            source=self._source,
        )

    def _state_for(self, idle_seconds: int) -> ActivityState:
        if idle_seconds >= self._away_after_seconds:
            return ActivityState.AWAY
        if idle_seconds >= self._idle_after_seconds:
            return ActivityState.IDLE
        return ActivityState.ACTIVE

    def _validate_thresholds(
        self,
        idle_after_seconds: int,
        away_after_seconds: int,
    ) -> None:
        if idle_after_seconds <= 0:
            raise ValueError("idle_after_seconds must be greater than zero.")
        if away_after_seconds <= idle_after_seconds:
            raise ValueError(
                "away_after_seconds must be greater than idle_after_seconds."
            )


def _now() -> datetime:
    return datetime.now(tz=UTC)
