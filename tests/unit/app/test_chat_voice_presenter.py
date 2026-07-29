"""Tests for presenting voice events on the chat surface."""

from __future__ import annotations

import unittest

from project_akiha.app.chat_voice_presenter import ChatVoicePresenter
from project_akiha.config import VoiceConfig
from project_akiha.core.events.bus import EventBus
from project_akiha.core.events.types import EventType


class _ChatVoiceSurface:
    def __init__(self) -> None:
        self.capabilities: tuple[bool, bool] | None = None
        self.states: list[tuple[str, str]] = []
        self.transcripts: list[str] = []
        self.replay_availability: list[bool] = []
        self.errors: list[str] = []

    def set_voice_capabilities(
        self,
        input_enabled: bool,
        output_enabled: bool,
    ) -> None:
        self.capabilities = (input_enabled, output_enabled)

    def set_voice_state(self, state: str, operation: str = "none") -> None:
        self.states.append((state, operation))

    def insert_voice_transcript(self, text: str) -> None:
        self.transcripts.append(text)

    def set_voice_replay_available(self, available: bool) -> None:
        self.replay_availability.append(available)

    def append_error(self, content: str) -> None:
        self.errors.append(content)


class ChatVoicePresenterTest(unittest.TestCase):
    """Verify voice events are validated before reaching ChatWindow."""

    def test_initializes_surface_from_config_and_runtime_state(self) -> None:
        bus = EventBus()
        surface = _ChatVoiceSurface()

        ChatVoicePresenter(
            event_bus=bus,
            surface=surface,
            config=VoiceConfig(enabled=True),
            initial_state="idle",
        )

        self.assertEqual(surface.capabilities, (True, True))
        self.assertEqual(surface.states, [("idle", "none")])

    def test_config_disables_only_unavailable_capability(self) -> None:
        bus = EventBus()
        surface = _ChatVoiceSurface()
        presenter = ChatVoicePresenter(
            event_bus=bus,
            surface=surface,
            config=VoiceConfig(),
            initial_state="muted",
        )

        presenter.apply_config(VoiceConfig(enabled=True, input_provider="disabled"))

        self.assertEqual(surface.capabilities, (False, True))

    def test_presents_state_with_operation(self) -> None:
        bus = EventBus()
        surface = _ChatVoiceSurface()
        ChatVoicePresenter(bus, surface, VoiceConfig(), "muted")

        bus.publish(
            EventType.VOICE_STATE_CHANGED,
            {"state": "thinking", "operation": "input"},
        )

        self.assertEqual(surface.states[-1], ("thinking", "input"))

    def test_places_transcript_in_editable_surface(self) -> None:
        bus = EventBus()
        surface = _ChatVoiceSurface()
        ChatVoicePresenter(bus, surface, VoiceConfig(), "muted")

        bus.publish(
            EventType.VOICE_TRANSCRIPT_READY,
            {"text": "おはようございます。"},
        )

        self.assertEqual(surface.transcripts, ["おはようございます。"])

    def test_ignores_malformed_state_and_transcript_events(self) -> None:
        bus = EventBus()
        surface = _ChatVoiceSurface()
        ChatVoicePresenter(bus, surface, VoiceConfig(), "muted")

        bus.publish(EventType.VOICE_STATE_CHANGED, {"state": 42})
        bus.publish(EventType.VOICE_TRANSCRIPT_READY, {"text": " "})

        self.assertEqual(surface.states, [("muted", "none")])
        self.assertEqual(surface.transcripts, [])

    def test_presents_privacy_safe_voice_error(self) -> None:
        bus = EventBus()
        surface = _ChatVoiceSurface()
        ChatVoicePresenter(bus, surface, VoiceConfig(), "muted")

        bus.publish(
            EventType.VOICE_ERROR_OCCURRED,
            {"message": "Microphone unavailable."},
        )

        self.assertEqual(surface.errors, ["Voice: Microphone unavailable."])

    def test_presents_valid_replay_availability(self) -> None:
        bus = EventBus()
        surface = _ChatVoiceSurface()
        ChatVoicePresenter(bus, surface, VoiceConfig(), "muted")

        bus.publish(
            EventType.VOICE_REPLAY_AVAILABILITY_CHANGED,
            {"available": True},
        )
        bus.publish(
            EventType.VOICE_REPLAY_AVAILABILITY_CHANGED,
            {"available": "yes"},
        )

        self.assertEqual(surface.replay_availability, [True])


if __name__ == "__main__":
    unittest.main()
