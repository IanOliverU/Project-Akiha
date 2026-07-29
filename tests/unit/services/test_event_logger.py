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


if __name__ == "__main__":
    unittest.main()
