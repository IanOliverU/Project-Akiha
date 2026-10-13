"""Bounded local reminder parsing and existing action-boundary adapters."""

from __future__ import annotations

import re

from project_akiha.core.actions import (
    ActionExecutionResult,
    ActionRequest,
    ActionStatus,
)
from project_akiha.core.actions.clarification import request_fingerprint
from project_akiha.core.utilities.reminders import REMINDER_ACTIONS
from project_akiha.services.timer_schedule import TimerScheduleService


def parse_reminder_command(text: str, correlation_id: str) -> ActionRequest | None:
    value = text.strip().rstrip(".!?").strip()
    parameters = {"service": "reminders"}
    if re.fullmatch(r"(?:list|show(?: me)?) (?:my )?reminders|/reminders", value, re.I):
        return ActionRequest(correlation_id, "reminders.list", "chat", parameters)
    match = re.fullmatch(r"cancel reminder(?: (\S+))?", value, re.I)
    if match:
        if match[1]:
            parameters["reminder_id"] = match[1]
        return ActionRequest(correlation_id, "reminders.cancel", "chat", parameters)
    match = re.fullmatch(
        r"snooze reminder(?: (\S+))?(?: for (\d{1,7}) (seconds?|minutes?|hours?))?",
        value,
        re.I,
    )
    if match:
        if match[1]:
            parameters["reminder_id"] = match[1]
        if match[2]:
            parameters["duration_seconds"] = (
                int(match[2]) * {"s": 1, "m": 60, "h": 3600}[match[3][0].lower()]
            )
        return ActionRequest(correlation_id, "reminders.snooze", "chat", parameters)
    if not re.match(r"^(?:(?:set|create) (?:a )?reminder\b|remind me\b)", value, re.I):
        return None
    if re.fullmatch(r"(?:set|create) (?:a )?reminder|remind me", value, re.I):
        return ActionRequest(correlation_id, "reminders.create", "chat", parameters)
    match = re.fullmatch(
        r"(?:(?:set|create) (?:a )?reminder|remind me) (?:at|on) "
        r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}) ([A-Za-z_+/-]{1,64})"
        r"(?: occurrence ([01]))?(?: (?:named|called) ([\w -]{1,64}))?",
        value,
        re.I,
    )
    if match:
        parameters.update(local_time=match[1] + "T" + match[2], timezone=match[3])
        if match[4]:
            parameters["fold"] = int(match[4])
        if match[5]:
            parameters["label"] = match[5].strip()
    else:
        parameters["local_time"] = "invalid"
    return ActionRequest(correlation_id, "reminders.create", "chat", parameters)


class ReminderActionExecutor:
    def __init__(self, service: TimerScheduleService | None, action_id: str) -> None:
        self.service = service
        self.action_id = action_id
        self.executor_id = action_id.replace(".", "_")

    async def execute(self, action, *, cancellation_token) -> ActionExecutionResult:
        if cancellation_token.is_cancelled:
            return ActionExecutionResult(
                ActionStatus.CANCELLED, "The reminder action was cancelled."
            )
        if self.service is None or self.service.reminders is None:
            return ActionExecutionResult(
                ActionStatus.UNAVAILABLE, "Local reminders are unavailable."
            )
        p = action.parameters
        try:
            if self.action_id == "reminders.create":
                r = self.service.create_reminder(
                    action.request.correlation_id,
                    request_fingerprint(action.request),
                    p["local_time"],
                    p["timezone"],
                    p.get("label", ""),
                    p.get("fold"),
                )
                summary = (
                    f"Reminder {r.reminder_id}: {r.status.value}; "
                    f"due {r.due_at.isoformat()} ({r.timezone})."
                )
            elif self.action_id == "reminders.list":
                records = self.service.list_reminders()
                summary = (
                    "No active reminders."
                    if not records
                    else "Active reminders:\n"
                    + "\n".join(
                        f"{r.reminder_id}: {r.due_at.isoformat()} ({r.timezone})."
                        for r in records
                    )
                )
            elif self.action_id == "reminders.cancel":
                summary = (
                    "Reminder cancelled."
                    if self.service.cancel_reminder(p["reminder_id"])
                    else "Reminder is absent or already terminal."
                )
            else:
                r = self.service.snooze_reminder(
                    action.request.correlation_id,
                    request_fingerprint(action.request),
                    p["reminder_id"],
                    p["duration_seconds"],
                )
                summary = (
                    f"Reminder {r.reminder_id}: {r.status.value}; "
                    f"due {r.due_at.isoformat()}."
                )
        except ValueError:
            return ActionExecutionResult(
                ActionStatus.DENIED,
                (
                    "Reminder unavailable. Use a future explicit "
                    "date, time and timezone, or a current reminder "
                    "ID."
                ),
            )
        return ActionExecutionResult(ActionStatus.SUCCESS, summary)


def build_reminder_executors(service: TimerScheduleService | None):
    return tuple(
        ReminderActionExecutor(service, action_id) for action_id in REMINDER_ACTIONS
    )
