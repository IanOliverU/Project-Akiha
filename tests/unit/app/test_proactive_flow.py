"""Integration-style tests for the proactive behavior flow."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from project_akiha.app.activity_controller import ActivityController
from project_akiha.app.mood_controller import MoodController
from project_akiha.app.proactive_controller import ProactiveController
from project_akiha.app.proactive_delivery_controller import ProactiveDeliveryController
from project_akiha.config import BehaviorConfig
from project_akiha.core.behavior import (
    CompanionMood,
    CompanionPresenceMapper,
    MoodEngine,
    NotificationPolicy,
    ProactiveDeliveryService,
    ProactiveSuggestionEngine,
)
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.services.behavior_history import BehaviorHistoryRecorder

_IDLE_MESSAGE = "You've been quiet for a bit. Want to stretch or take a short pause?"


class ProactiveFlowTest(unittest.TestCase):
    """Verify activity can flow through proactive delivery and mood surfaces."""

    def test_idle_activity_flows_to_chat_delivery_history_and_presence(self) -> None:
        bus = EventBus()
        config = BehaviorConfig(
            idle_after_seconds=300,
            away_after_seconds=900,
            proactive_enabled=True,
            quiet_hours_enabled=False,
        )
        surface = _Surface(chat_visible=True, tray_available=True)
        repository = _RecordingBehaviorRepository()
        mood_events: list[Event] = []
        presence_updates: list[str] = []
        presence_mapper = CompanionPresenceMapper()

        activity_controller = ActivityController(bus, config, initial_time=_start())
        MoodController(bus, MoodEngine(initial_time=_start()))
        ProactiveController(
            bus,
            ProactiveSuggestionEngine(NotificationPolicy(config)),
        )
        BehaviorHistoryRecorder(bus, repository)
        ProactiveDeliveryController(bus, ProactiveDeliveryService(), surface)
        bus.subscribe(EventType.MOOD_STATE_CHANGED, mood_events.append)
        bus.subscribe(
            EventType.MOOD_STATE_CHANGED,
            lambda event: presence_updates.append(
                presence_mapper.text_for(
                    _mood_from_payload(event.payload),
                )
            ),
        )

        activity = activity_controller.tick(_start() + timedelta(seconds=300))

        self.assertEqual(activity.state.value, "idle")
        self.assertEqual(
            surface.chat_suggestions,
            (("idle_check_in", _IDLE_MESSAGE),),
        )
        self.assertEqual(surface.tray_messages, ())
        self.assertEqual(
            [record.event_type for record in repository.records],
            [
                "proactive.suggestion_ready",
                "proactive.suggestion_delivered",
            ],
        )
        self.assertEqual(repository.records[0].kind, "idle_check_in")
        self.assertEqual(repository.records[1].payload["channel"], "chat_notice")
        self.assertEqual(mood_events[-1].payload["mood"], "checking_in")
        self.assertEqual(presence_updates[-1], "Akiha is checking in.")

    def test_hidden_chat_flow_uses_tray_and_records_delivery_channel(self) -> None:
        bus = EventBus()
        config = BehaviorConfig(
            idle_after_seconds=300,
            away_after_seconds=900,
            proactive_enabled=True,
            quiet_hours_enabled=False,
        )
        surface = _Surface(chat_visible=False, tray_available=True)
        repository = _RecordingBehaviorRepository()

        activity_controller = ActivityController(bus, config, initial_time=_start())
        ProactiveController(
            bus,
            ProactiveSuggestionEngine(NotificationPolicy(config)),
        )
        BehaviorHistoryRecorder(bus, repository)
        ProactiveDeliveryController(bus, ProactiveDeliveryService(), surface)

        activity_controller.tick(_start() + timedelta(seconds=300))

        self.assertEqual(surface.chat_suggestions, ())
        self.assertEqual(
            surface.tray_messages,
            (("Akiha", _IDLE_MESSAGE),),
        )
        self.assertEqual(repository.records[-1].payload["channel"], "tray_message")


class _Surface:
    def __init__(
        self,
        *,
        chat_visible: bool,
        tray_available: bool,
    ) -> None:
        self._chat_visible = chat_visible
        self._tray_available = tray_available
        self._chat_suggestions: list[tuple[str, str]] = []
        self._tray_messages: list[tuple[str, str]] = []

    @property
    def chat_suggestions(self) -> tuple[tuple[str, str], ...]:
        return tuple(self._chat_suggestions)

    @property
    def tray_messages(self) -> tuple[tuple[str, str], ...]:
        return tuple(self._tray_messages)

    def is_chat_visible(self) -> bool:
        return self._chat_visible

    def append_chat_suggestion(self, kind: str, message: str) -> None:
        self._chat_suggestions.append((kind, message))

    def can_show_tray_message(self) -> bool:
        return self._tray_available

    def show_tray_message(self, title: str, message: str) -> None:
        self._tray_messages.append((title, message))


class _RecordedBehaviorEvent:
    def __init__(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        kind: str | None,
    ) -> None:
        self.event_type = event_type
        self.payload = payload
        self.kind = kind


class _RecordingBehaviorRepository:
    def __init__(self) -> None:
        self._records: list[_RecordedBehaviorEvent] = []

    @property
    def records(self) -> tuple[_RecordedBehaviorEvent, ...]:
        return tuple(self._records)

    async def record_event(
        self,
        event_type: str,
        payload: dict[str, object],
        kind: str | None = None,
    ) -> object:
        self._records.append(
            _RecordedBehaviorEvent(
                event_type=event_type,
                payload=payload,
                kind=kind,
            )
        )
        return object()


def _mood_from_payload(payload: dict[str, object]):
    return CompanionMood(str(payload["mood"]))


def _start() -> datetime:
    return datetime(2026, 7, 24, 10, 0, tzinfo=UTC)


if __name__ == "__main__":
    unittest.main()
