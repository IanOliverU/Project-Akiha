"""One monotonic schedule owner; wall time is used only for restart recovery."""

from __future__ import annotations

from datetime import timedelta
from threading import RLock
from uuid import uuid4

from project_akiha.core.utilities.clock import UtilityClock
from project_akiha.core.utilities.timers import (
    TIMER_RECOVERY_GRACE_SECONDS,
    TimerRecord,
    TimerRepository,
    TimerStatus,
    validate_timer_id,
    validate_timer_input,
)


class TimerScheduleService:
    def __init__(self, repository: TimerRepository, clock: UtilityClock) -> None:
        self.repository = repository
        self.clock = clock
        self._lock = RLock()
        self._closed = False
        wall = clock.now_utc()
        mono = clock.monotonic_seconds()
        self._deadlines = {}
        self._missed = set()
        for record in repository.pending():
            remaining = (record.due_at - wall).total_seconds()
            self._deadlines[record.timer_id] = mono + max(
                0, min(record.duration_seconds, remaining)
            )
            if remaining < -TIMER_RECOVERY_GRACE_SECONDS:
                self._missed.add(record.timer_id)

    def _open(self) -> None:
        if self._closed:
            raise RuntimeError("Timer service is closed.")

    def create(
        self, request_id: str, digest: str, seconds: int, label: str = ""
    ) -> TimerRecord:
        validate_timer_input(seconds, label)
        with self._lock:
            self._open()
            now = self.clock.now_utc()
            mono = self.clock.monotonic_seconds()
            proposed = TimerRecord(
                "timer-" + uuid4().hex,
                request_id,
                digest,
                label,
                seconds,
                now,
                now + timedelta(seconds=seconds),
                TimerStatus.PENDING,
            )
            record = self.repository.create(proposed)
            if record.timer_id == proposed.timer_id:
                self._deadlines[record.timer_id] = mono + seconds
            return record

    def list(self) -> tuple[TimerRecord, ...]:
        with self._lock:
            self._open()
            return self.repository.pending()

    def inspect(self, timer_id: str) -> tuple[TimerRecord | None, int]:
        validate_timer_id(timer_id)
        with self._lock:
            self._open()
            record = self.repository.get(timer_id)
            remaining = max(
                0, self._deadlines.get(timer_id, 0) - self.clock.monotonic_seconds()
            )
            return record, int(remaining + 0.999999)

    def cancel(self, timer_id: str) -> bool:
        validate_timer_id(timer_id)
        with self._lock:
            self._open()
            changed = self.repository.cancel(timer_id, self.clock.now_utc())
            self._deadlines.pop(timer_id, None)
            self._missed.discard(timer_id)
            return changed

    def tick(self) -> tuple[TimerRecord, ...]:
        with self._lock:
            if self._closed:
                return ()
            now = self.clock.monotonic_seconds()
            ready = []
            for timer_id, deadline in tuple(self._deadlines.items()):
                if now < deadline:
                    continue
                record = self.repository.claim_expiry(
                    timer_id, self.clock.now_utc(), missed=timer_id in self._missed
                )
                self._deadlines.pop(timer_id, None)
                self._missed.discard(timer_id)
                if record is not None:
                    ready.append(record)
            return tuple(ready)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._deadlines.clear()
            self._missed.clear()
