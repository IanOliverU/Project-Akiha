"""Injectable clock boundary for timers, reminders, and expiring proposals."""

from __future__ import annotations

from datetime import UTC, datetime
from time import monotonic
from typing import Protocol, runtime_checkable


@runtime_checkable
class UtilityClock(Protocol):
    """Expose separate wall and monotonic clocks for deterministic scheduling."""

    def now_utc(self) -> datetime:
        """Return the timezone-aware wall clock used for durable timestamps."""

    def monotonic_seconds(self) -> float:
        """Return the process-local clock used for elapsed durations."""


class SystemUtilityClock:
    """Production utility clock backed only by the Python standard library."""

    def now_utc(self) -> datetime:
        return datetime.now(tz=UTC)

    def monotonic_seconds(self) -> float:
        return monotonic()
