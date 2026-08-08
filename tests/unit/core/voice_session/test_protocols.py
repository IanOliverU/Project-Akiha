"""Contract-shape tests for provider-neutral voice protocols."""

from __future__ import annotations

import unittest

from project_akiha.core.voice_session import (
    LiveSessionEventSink,
    StreamingSpeechRecognizer,
)


class VoiceSessionProtocolTest(unittest.TestCase):
    def test_live_callbacks_belong_to_live_event_sink_only(self) -> None:
        live_members = set(LiveSessionEventSink.__dict__)
        recognizer_members = set(StreamingSpeechRecognizer.__dict__)

        self.assertIn("session_state_changed", live_members)
        self.assertIn("capabilities_received", live_members)
        self.assertNotIn("session_state_changed", recognizer_members)
        self.assertNotIn("capabilities_received", recognizer_members)


if __name__ == "__main__":
    unittest.main()
