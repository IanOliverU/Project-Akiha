"""Tests for app-level proactive delivery wiring."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from project_akiha.app.proactive_delivery_controller import ProactiveDeliveryController
from project_akiha.core.behavior import ProactiveDeliveryService
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType


class ProactiveDeliveryControllerTest(unittest.TestCase):
    """Verify proactive suggestion delivery events."""

    def test_ready_suggestion_is_delivered_and_result_is_published(self) -> None:
        bus = EventBus()
        delivered: list[Event] = []
        surface = _Surface(chat_visible=True, tray_available=True)
        bus.subscribe(EventType.PROACTIVE_SUGGESTION_DELIVERED, delivered.append)
        ProactiveDeliveryController(bus, ProactiveDeliveryService(), surface)

        bus.publish(EventType.PROACTIVE_SUGGESTION_READY, _payload())

        self.assertEqual(surface.chat_notices, ("Need a short break?",))
        self.assertEqual(len(delivered), 1)
        self.assertTrue(delivered[0].payload["delivered"])
        self.assertEqual(delivered[0].payload["channel"], "chat_notice")
        self.assertEqual(delivered[0].payload["kind"], "idle_check_in")

    def test_hidden_chat_uses_tray_delivery(self) -> None:
        bus = EventBus()
        delivered: list[Event] = []
        surface = _Surface(chat_visible=False, tray_available=True)
        bus.subscribe(EventType.PROACTIVE_SUGGESTION_DELIVERED, delivered.append)
        ProactiveDeliveryController(bus, ProactiveDeliveryService(), surface)

        bus.publish(EventType.PROACTIVE_SUGGESTION_READY, _payload())

        self.assertEqual(surface.tray_messages, (("Akiha", "Need a short break?"),))
        self.assertEqual(delivered[0].payload["channel"], "tray_message")

    def test_invalid_payload_is_ignored(self) -> None:
        bus = EventBus()
        delivered: list[Event] = []
        surface = _Surface(chat_visible=True, tray_available=True)
        bus.subscribe(EventType.PROACTIVE_SUGGESTION_DELIVERED, delivered.append)
        ProactiveDeliveryController(bus, ProactiveDeliveryService(), surface)

        bus.publish(EventType.PROACTIVE_SUGGESTION_READY, {"message": "Missing fields"})

        self.assertEqual(surface.chat_notices, ())
        self.assertEqual(delivered, [])

    def test_failed_delivery_still_publishes_result(self) -> None:
        bus = EventBus()
        delivered: list[Event] = []
        surface = _Surface(chat_visible=False, tray_available=False)
        bus.subscribe(EventType.PROACTIVE_SUGGESTION_DELIVERED, delivered.append)
        ProactiveDeliveryController(bus, ProactiveDeliveryService(), surface)

        bus.publish(EventType.PROACTIVE_SUGGESTION_READY, _payload())

        self.assertFalse(delivered[0].payload["delivered"])
        self.assertEqual(delivered[0].payload["channel"], "none")
        self.assertEqual(delivered[0].payload["reason"], "no_available_surface")


class _Surface:
    def __init__(
        self,
        *,
        chat_visible: bool,
        tray_available: bool,
    ) -> None:
        self._chat_visible = chat_visible
        self._tray_available = tray_available
        self._chat_notices: list[str] = []
        self._tray_messages: list[tuple[str, str]] = []

    @property
    def chat_notices(self) -> tuple[str, ...]:
        return tuple(self._chat_notices)

    @property
    def tray_messages(self) -> tuple[tuple[str, str], ...]:
        return tuple(self._tray_messages)

    def is_chat_visible(self) -> bool:
        return self._chat_visible

    def append_chat_notice(self, message: str) -> None:
        self._chat_notices.append(message)

    def can_show_tray_message(self) -> bool:
        return self._tray_available

    def show_tray_message(self, title: str, message: str) -> None:
        self._tray_messages.append((title, message))


def _payload() -> dict[str, object]:
    return {
        "kind": "idle_check_in",
        "message": "Need a short break?",
        "urgency": "low",
        "created_at": datetime(2026, 7, 24, 12, 0, tzinfo=UTC).isoformat(),
    }


if __name__ == "__main__":
    unittest.main()
