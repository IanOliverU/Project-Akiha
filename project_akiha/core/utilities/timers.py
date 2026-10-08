"""Bounded, framework-free one-shot timer contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol

MAX_TIMER_SECONDS = 7 * 24 * 60 * 60
MAX_ACTIVE_TIMERS = 100
TIMER_RECOVERY_GRACE_SECONDS = 3600
TIMER_ACTIONS = ("timers.create", "timers.list", "timers.inspect", "timers.cancel")
TIMER_CAPABILITY = "timers.manage"


class TimerStatus(StrEnum):
    PENDING = "pending"
    ELAPSED = "elapsed"
    CANCELLED = "cancelled"
    MISSED = "missed"


class TimerNotificationSource(StrEnum):
    TIMERS = "timers"


class TimerNotificationKind(StrEnum):
    ELAPSED = "timers.elapsed"


def validate_timer_id(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"timer-[a-f0-9]{32}", value) is None:
        raise ValueError("Invalid timer identifier.")
    return value


def validate_timer_input(seconds: int, label: str) -> None:
    if type(seconds) is not int or not 1 <= seconds <= MAX_TIMER_SECONDS:
        raise ValueError("Timer duration must be 1 to 604800 whole seconds.")
    if (
        not isinstance(label, str)
        or len(label) > 64
        or any(not (char.isalnum() or char in " -_") for char in label)
    ):
        raise ValueError("Timer labels use at most 64 letters, digits, spaces or -_.")


@dataclass(frozen=True, slots=True)
class TimerRecord:
    timer_id: str
    request_id: str
    request_digest: str
    label: str = field(repr=False)
    duration_seconds: int
    created_at: datetime
    due_at: datetime
    status: TimerStatus
    notification_id: int | None = None

    def __post_init__(self) -> None:
        validate_timer_id(self.timer_id)
        validate_timer_input(self.duration_seconds, self.label)
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", self.request_id) is None:
            raise ValueError("Invalid timer request identifier.")
        if re.fullmatch(r"[a-f0-9]{64}", self.request_digest) is None:
            raise ValueError("Invalid timer request fingerprint.")
        if not isinstance(self.status, TimerStatus):
            raise ValueError("Invalid timer status.")
        if self.created_at.tzinfo is None or self.due_at.tzinfo is None:
            raise ValueError("Timer timestamps require a timezone.")
        if (self.due_at - self.created_at).total_seconds() != self.duration_seconds:
            raise ValueError("Timer wall deadline does not match its duration.")


class TimerRepository(Protocol):
    def create(self, record: TimerRecord) -> TimerRecord: ...
    def pending(self) -> tuple[TimerRecord, ...]: ...
    def get(self, timer_id: str) -> TimerRecord | None: ...
    def cancel(self, timer_id: str, now: datetime) -> bool: ...
    def claim_expiry(
        self, timer_id: str, now: datetime, *, missed: bool
    ) -> TimerRecord | None: ...
