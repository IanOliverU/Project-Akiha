"""Typed local timer commands and adapters for the existing action service."""

from __future__ import annotations

import re

from project_akiha.core.actions import (
    ActionExecutionResult,
    ActionRequest,
    ActionStatus,
)
from project_akiha.core.actions.clarification import request_fingerprint
from project_akiha.core.utilities.timers import TIMER_ACTIONS
from project_akiha.services.timer_schedule import TimerScheduleService


def parse_timer_command(text: str, correlation_id: str) -> ActionRequest | None:
    text = text.strip().rstrip(".!?").strip()
    action = None
    parameters = {"service": "timers"}
    if re.fullmatch(r"(?:list|show(?: me)?) (?:my )?timers|/timers", text, re.I):
        action = "timers.list"
    elif match := re.fullmatch(
        r"(?:inspect|show|cancel) timer(?: (\S+))?|/timer (inspect|cancel)(?: (\S+))?",
        text,
        re.I,
    ):
        verb = match[2] or text.split()[0]
        action = "timers.cancel" if verb.casefold() == "cancel" else "timers.inspect"
        if timer_id := match[1] or match[3]:
            parameters["timer_id"] = timer_id
    elif re.match(r"^(?:(?:set|start|create) (?:a )?timer\b|/timer\b)", text, re.I):
        action = "timers.create"
        if re.search(
            r"(?:;|\band\s+(?:then\s+)?(?:open|play|set|start|cancel|create)\b)",
            text,
            re.I,
        ):
            parameters["duration_seconds"] = -1
        elif re.fullmatch(r"(?:set|start|create) (?:a )?timer|/timer", text, re.I):
            pass  # Existing Phase 13B local integer clarification.
        elif match := re.fullmatch(
            r"(?:(?:set|start|create) (?:a )?timer(?: for)?|/timer) "
            r"([0-9]{1,7}) (seconds?|minutes?|hours?)"
            r"(?: (?:named|called) ([\w -]{1,64}))?",
            text,
            re.I,
        ):
            multiplier = {"s": 1, "m": 60, "h": 3600}[match[2][0].lower()]
            parameters["duration_seconds"] = int(match[1]) * multiplier
            if match[3]:
                parameters["label"] = match[3].strip()
        else:
            # Bound timer-shaped invalid/compound input locally; never execute a
            # prefix or let uncertain durations become arbitrary provider actions.
            parameters["duration_seconds"] = -1
    if action is None:
        return None
    return ActionRequest(correlation_id, action, "chat", parameters)


class TimerActionExecutor:
    def __init__(self, service: TimerScheduleService | None, action_id: str) -> None:
        self.service = service
        self.action_id = action_id
        self.executor_id = action_id.replace(".", "_")

    async def execute(self, action, *, cancellation_token) -> ActionExecutionResult:
        if cancellation_token.is_cancelled:
            return ActionExecutionResult(
                ActionStatus.CANCELLED, "The timer action was cancelled."
            )
        if self.service is None:
            return ActionExecutionResult(
                ActionStatus.UNAVAILABLE, "Local timers are unavailable."
            )
        parameters = action.parameters
        if self.action_id == "timers.create":
            # Label and duration never enter the action audit's normalized target.
            record = self.service.create(
                action.request.correlation_id,
                request_fingerprint(action.request),
                parameters["duration_seconds"],
                parameters.get("label", ""),
            )
            summary = (
                f"Timer {record.timer_id}: {record.status.value}; "
                f"duration {record.duration_seconds} seconds."
            )
        elif self.action_id == "timers.list":
            records = self.service.list()
            summary = (
                "No active timers."
                if not records
                else "Active timers:\n"
                + "\n".join(
                    f"{r.timer_id}: {self.service.inspect(r.timer_id)[1]} "
                    "seconds remaining."
                    for r in records
                )
            )
        elif self.action_id == "timers.inspect":
            record, remaining = self.service.inspect(parameters["timer_id"])
            summary = (
                "Timer not found."
                if record is None
                else f"Timer {record.timer_id}: {record.status.value}; "
                f"{remaining} seconds remaining."
            )
        else:
            changed = self.service.cancel(parameters["timer_id"])
            summary = (
                "Timer cancelled."
                if changed
                else "Timer is absent or already terminal."
            )
        return ActionExecutionResult(ActionStatus.SUCCESS, summary)


def build_timer_executors(service: TimerScheduleService | None):
    return tuple(TimerActionExecutor(service, action_id) for action_id in TIMER_ACTIONS)
