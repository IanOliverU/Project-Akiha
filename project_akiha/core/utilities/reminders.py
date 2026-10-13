"""One-shot local reminder identity and explicit timezone interpretation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from project_akiha.core.utilities.timers import TimerStatus, validate_timer_input

MAX_REMINDER_SECONDS = 366 * 86400
REMINDER_ACTIONS = (
    "reminders.create",
    "reminders.list",
    "reminders.cancel",
    "reminders.snooze",
)


class AmbiguousReminderTime(ValueError):
    """A repeated local time requires the user's explicit occurrence choice."""


class NonexistentReminderTime(ValueError):
    """A skipped local time requires a different local date/time."""


def reminder_time(local_time: str, timezone: str, fold: int | None = None) -> datetime:
    if not isinstance(local_time, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", local_time
    ):
        raise ValueError("Use an explicit date and time: YYYY-MM-DDTHH:MM.")
    if not isinstance(timezone, str) or len(timezone) > 64:
        raise ValueError("Use an explicit IANA timezone.")
    if fold is not None and (type(fold) is not int or fold not in (0, 1)):
        raise ValueError("Occurrence must be 0 or 1.")
    try:
        zone = ZoneInfo(timezone)
        local = datetime.fromisoformat(local_time)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise ValueError("The date, time or timezone is unavailable.") from error
    valid = {}
    for occurrence in (0, 1):
        candidate = local.replace(tzinfo=zone, fold=occurrence).astimezone(UTC)
        if candidate.astimezone(zone).replace(tzinfo=None) == local:
            valid[occurrence] = candidate
    if not valid:
        raise NonexistentReminderTime(
            "That local time does not exist; choose another time."
        )
    if len(set(valid.values())) > 1 and fold is None:
        raise AmbiguousReminderTime("Choose occurrence 0 (first) or 1 (second).")
    return valid[fold if fold is not None else min(valid)]


def validate_reminder_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"reminder-[a-f0-9]{32}", value):
        raise ValueError("Invalid reminder identifier.")
    return value


@dataclass(frozen=True, slots=True)
class ReminderRecord:
    reminder_id: str
    request_id: str
    request_digest: str
    label: str = field(repr=False)
    timezone: str
    created_at: datetime
    due_at: datetime
    status: TimerStatus
    notification_id: int | None = None

    def __post_init__(self) -> None:
        validate_reminder_id(self.reminder_id)
        validate_timer_input(1, self.label)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", self.request_id):
            raise ValueError("Invalid reminder request identity.")
        if not re.fullmatch(r"[a-f0-9]{64}", self.request_digest):
            raise ValueError("Invalid reminder fingerprint.")
        if self.created_at.tzinfo is None or self.due_at.tzinfo is None:
            raise ValueError("Reminder timestamps require a timezone.")
        if (
            not 0
            < (self.due_at - self.created_at).total_seconds()
            <= MAX_REMINDER_SECONDS
        ):
            raise ValueError("Reminder time must be within the next 366 days.")
        ZoneInfo(self.timezone)
        if not isinstance(self.status, TimerStatus):
            raise ValueError("Invalid reminder status.")
