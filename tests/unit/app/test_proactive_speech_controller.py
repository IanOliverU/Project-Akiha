"""Tests for policy-gated proactive speech routing."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from project_akiha.app.activity_controller import ActivityController
from project_akiha.app.assistant_speech_controller import AssistantSpeechController
from project_akiha.app.proactive_controller import ProactiveController
from project_akiha.app.proactive_delivery_controller import ProactiveDeliveryController
from project_akiha.app.proactive_speech_controller import ProactiveSpeechController
from project_akiha.app.voice_controller import VoiceController
from project_akiha.config import BehaviorConfig, VoiceConfig
from project_akiha.core.behavior import (
    NotificationPolicy,
    ProactiveDeliveryService,
    ProactiveSuggestionEngine,
)
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType


class ProactiveSpeechControllerTest(unittest.TestCase):
    """Verify only successfully delivered, opted-in nudges are spoken."""

    def test_delivered_supported_suggestion_is_spoken(self) -> None:
        bus, requests = _speech_bus()
        ProactiveSpeechController(bus, _assistant_speech(bus))

        _publish_delivery(bus)

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].payload["source"], "proactive_suggestion")
        self.assertIsInstance(requests[0].payload["text"], str)
        self.assertTrue(requests[0].payload["text"])

    def test_delivered_pet_need_uses_structured_local_line(self) -> None:
        bus, requests = _speech_bus()
        ProactiveSpeechController(bus, _assistant_speech(bus))

        _publish_delivery(bus, kind="pet_need_energy_low")

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].payload["source"], "proactive_suggestion")

    def test_external_notice_uses_validated_rendered_message(self) -> None:
        bus, requests = _speech_bus()
        ProactiveSpeechController(bus, _assistant_speech(bus))

        bus.publish(
            EventType.PROACTIVE_SUGGESTION_DELIVERED,
            _delivery_payload(
                kind="external.gmail.interview_candidate",
                message="An interview email may have arrived.",
                speech_message="Ian-sama, an interview email appears to have arrived.",
            ),
        )

        self.assertEqual(len(requests), 1)
        self.assertEqual(
            requests[0].payload["text"],
            "Ian-sama, an interview email appears to have arrived.",
        )

    def test_failed_or_unknown_delivery_is_not_spoken(self) -> None:
        for payload in (
            _delivery_payload(delivered=False),
            _delivery_payload(kind="unknown_kind"),
            {"delivered": True},
        ):
            with self.subTest(payload=payload):
                bus, requests = _speech_bus()
                ProactiveSpeechController(bus, _assistant_speech(bus))

                bus.publish(EventType.PROACTIVE_SUGGESTION_DELIVERED, payload)

                self.assertEqual(requests, [])

    def test_voice_busy_state_suppresses_proactive_speech(self) -> None:
        bus = EventBus()
        config = VoiceConfig(enabled=True, proactive_speech_enabled=True)
        voice = VoiceController(bus, config)
        requests: list[Event] = []
        bus.subscribe(EventType.VOICE_SPEAK_REQUESTED, requests.append)
        speech = AssistantSpeechController(bus, voice, config)
        ProactiveSpeechController(bus, speech)
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        _publish_delivery(bus)

        self.assertEqual(requests, [])

    def test_quiet_hours_prevent_delivery_and_speech(self) -> None:
        config = BehaviorConfig(
            proactive_enabled=True,
            idle_after_seconds=300,
            away_after_seconds=900,
            quiet_hours_enabled=True,
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
        )
        bus, requests = _complete_flow(config)
        activity = ActivityController(bus, config, initial_time=_at(22, 0))

        activity.tick(_at(22, 5))

        self.assertEqual(requests, [])

    def test_notification_cooldown_prevents_second_spoken_nudge(self) -> None:
        config = BehaviorConfig(
            proactive_enabled=True,
            idle_after_seconds=300,
            away_after_seconds=900,
            minimum_seconds_between_notifications=600,
        )
        bus, requests = _complete_flow(config)
        deliveries: list[Event] = []
        bus.subscribe(EventType.PROACTIVE_SUGGESTION_DELIVERED, deliveries.append)
        activity = ActivityController(bus, config, initial_time=_at(12, 0))

        activity.tick(_at(12, 5))
        bus.publish(EventType.VOICE_SPEAK_STOP_REQUESTED)
        activity.record_activity(_at(12, 6))
        activity.tick(_at(12, 11))

        self.assertEqual(len(requests), 1)
        self.assertEqual(len(deliveries), 1)


class _Surface:
    def is_chat_visible(self) -> bool:
        return True

    def append_chat_suggestion(self, kind: str, message: str) -> None:
        del kind, message

    def can_show_tray_message(self) -> bool:
        return False

    def show_tray_message(self, title: str, message: str) -> None:
        del title, message


def _speech_bus() -> tuple[EventBus, list[Event]]:
    bus = EventBus()
    requests: list[Event] = []
    bus.subscribe(EventType.VOICE_SPEAK_REQUESTED, requests.append)
    return bus, requests


def _assistant_speech(bus: EventBus) -> AssistantSpeechController:
    config = VoiceConfig(enabled=True, proactive_speech_enabled=True)
    return AssistantSpeechController(
        bus,
        VoiceController(bus, config),
        config,
    )


def _complete_flow(
    behavior_config: BehaviorConfig,
) -> tuple[EventBus, list[Event]]:
    bus, requests = _speech_bus()
    policy = NotificationPolicy(behavior_config)
    ProactiveController(bus, ProactiveSuggestionEngine(policy))
    ProactiveDeliveryController(bus, ProactiveDeliveryService(), _Surface())
    ProactiveSpeechController(bus, _assistant_speech(bus))
    return bus, requests


def _publish_delivery(bus: EventBus, *, kind: str = "idle_check_in") -> None:
    bus.publish(
        EventType.PROACTIVE_SUGGESTION_DELIVERED,
        _delivery_payload(kind=kind),
    )


def _delivery_payload(
    *,
    delivered: bool = True,
    kind: str = "idle_check_in",
    message: str = "Need a short break?",
    speech_message: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": kind,
        "delivered": delivered,
        "message": message,
        "urgency": "low",
        "created_at": _at(12, 0).isoformat(),
        "channel": "chat_notice",
        "reason": "chat_visible",
    }
    if speech_message is not None:
        payload["speech_message"] = speech_message
    return payload


def _at(hour: int, minute: int) -> datetime:
    return datetime(2026, 7, 30, hour, minute, tzinfo=UTC)


if __name__ == "__main__":
    unittest.main()
