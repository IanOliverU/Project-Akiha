"""Tests for proactive suggestion delivery routing."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from project_akiha.core.behavior import (
    DeliveryChannel,
    NotificationUrgency,
    ProactiveDeliveryRequest,
    ProactiveDeliveryService,
)


class ProactiveDeliveryServiceTest(unittest.TestCase):
    """Verify safe delivery channel selection."""

    def test_delivers_to_chat_notice_when_chat_is_visible(self) -> None:
        surface = _Surface(chat_visible=True, tray_available=True)

        result = ProactiveDeliveryService().deliver(_request(), surface)

        self.assertTrue(result.delivered)
        self.assertEqual(result.channel, DeliveryChannel.CHAT_NOTICE)
        self.assertEqual(surface.chat_notices, ("Need a short break?",))
        self.assertEqual(surface.tray_messages, ())

    def test_delivers_to_tray_when_chat_is_hidden(self) -> None:
        surface = _Surface(chat_visible=False, tray_available=True)

        result = ProactiveDeliveryService().deliver(_request(), surface)

        self.assertTrue(result.delivered)
        self.assertEqual(result.channel, DeliveryChannel.TRAY_MESSAGE)
        self.assertEqual(surface.chat_notices, ())
        self.assertEqual(surface.tray_messages, (("Akiha", "Need a short break?"),))

    def test_drops_when_no_surface_is_available(self) -> None:
        surface = _Surface(chat_visible=False, tray_available=False)

        result = ProactiveDeliveryService().deliver(_request(), surface)

        self.assertFalse(result.delivered)
        self.assertEqual(result.channel, DeliveryChannel.NONE)
        self.assertEqual(result.reason, "no_available_surface")

    def test_drops_empty_messages(self) -> None:
        surface = _Surface(chat_visible=True, tray_available=True)

        result = ProactiveDeliveryService().deliver(
            ProactiveDeliveryRequest(
                kind="idle_check_in",
                message=" ",
                urgency=NotificationUrgency.LOW,
                created_at=_now(),
            ),
            surface,
        )

        self.assertFalse(result.delivered)
        self.assertEqual(result.reason, "empty_message")
        self.assertEqual(surface.chat_notices, ())
        self.assertEqual(surface.tray_messages, ())


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


def _request() -> ProactiveDeliveryRequest:
    return ProactiveDeliveryRequest(
        kind="idle_check_in",
        message="Need a short break?",
        urgency=NotificationUrgency.LOW,
        created_at=_now(),
    )


def _now() -> datetime:
    return datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


if __name__ == "__main__":
    unittest.main()
