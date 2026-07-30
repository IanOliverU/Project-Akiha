"""Tests for high-level event diagnostics."""

from __future__ import annotations

import logging
import unittest
from unittest.mock import Mock

from project_akiha.core.events.bus import EventBus
from project_akiha.core.events.types import EventType
from project_akiha.services.event_logger import EventLogger


class EventLoggerTest(unittest.TestCase):
    """Verify failures use error-level diagnostics."""

    def test_voice_error_is_logged_at_error_level(self) -> None:
        bus = EventBus()
        logger = Mock(spec=logging.Logger)
        EventLogger(bus, logger)

        bus.publish(
            EventType.VOICE_ERROR_OCCURRED,
            {"code": "provider_unavailable"},
        )

        logger.error.assert_called_once()
        logger.info.assert_not_called()

    def test_spoken_text_is_redacted_from_event_log(self) -> None:
        bus = EventBus()
        logger = Mock(spec=logging.Logger)
        EventLogger(bus, logger)

        bus.publish(
            EventType.VOICE_SPEAK_REQUESTED,
            {"text": "Private assistant response.", "source": "replay"},
        )

        logged_arguments = logger.info.call_args.args
        self.assertNotIn("Private assistant response.", repr(logged_arguments))
        self.assertIn("text_present", repr(logged_arguments))
        self.assertIn("replay", repr(logged_arguments))

    def test_transcript_text_is_redacted_but_language_is_retained(self) -> None:
        bus = EventBus()
        logger = Mock(spec=logging.Logger)
        EventLogger(bus, logger)

        bus.publish(
            EventType.VOICE_TRANSCRIPT_READY,
            {"text": "Private transcript.", "detected_language": "ja"},
        )

        logged_arguments = logger.info.call_args.args
        self.assertNotIn("Private transcript.", repr(logged_arguments))
        self.assertIn("text_present", repr(logged_arguments))
        self.assertIn("ja", repr(logged_arguments))

    def test_partial_transcript_text_is_also_redacted(self) -> None:
        bus = EventBus()
        logger = Mock(spec=logging.Logger)
        EventLogger(bus, logger)

        bus.publish(
            EventType.VOICE_TRANSCRIPT_PARTIAL,
            {"text": "Private interim words.", "detected_language": "en"},
        )

        logged_arguments = logger.info.call_args.args
        self.assertNotIn("Private interim words.", repr(logged_arguments))
        self.assertIn("text_present", repr(logged_arguments))


if __name__ == "__main__":
    unittest.main()
