"""Tests for automatic assistant-reply speech policy."""

from __future__ import annotations

import unittest

from project_akiha.app.assistant_speech_controller import AssistantSpeechController
from project_akiha.app.voice_controller import VoiceController
from project_akiha.config import VoiceConfig
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState


class AssistantSpeechControllerTest(unittest.TestCase):
    """Verify only completed, permitted replies enter synthesis."""

    def test_enabled_automatic_speech_publishes_exact_assistant_text(self) -> None:
        bus, voice, controller, requests = _build(
            VoiceConfig(enabled=True, automatic_speech_enabled=True)
        )
        response = "  A completed assistant response.  "

        submitted = controller.submit_assistant_reply(response)

        self.assertTrue(submitted)
        self.assertEqual(requests[-1].payload["text"], response)
        self.assertEqual(requests[-1].payload["source"], "assistant_reply")
        self.assertEqual(voice.state, VoiceState.THINKING)

    def test_automatic_speech_is_opt_in(self) -> None:
        _, voice, controller, requests = _build(VoiceConfig(enabled=True))

        submitted = controller.submit_assistant_reply("Silent by default.")

        self.assertFalse(submitted)
        self.assertEqual(requests, [])
        self.assertEqual(voice.state, VoiceState.IDLE)

    def test_disabled_output_suppresses_automatic_speech(self) -> None:
        _, voice, controller, requests = _build(
            VoiceConfig(
                enabled=True,
                output_provider="disabled",
                automatic_speech_enabled=True,
            )
        )

        submitted = controller.submit_assistant_reply("Do not speak.")

        self.assertFalse(submitted)
        self.assertEqual(requests, [])
        self.assertEqual(voice.state, VoiceState.IDLE)

    def test_empty_response_is_ignored(self) -> None:
        _, voice, controller, requests = _build(
            VoiceConfig(enabled=True, automatic_speech_enabled=True)
        )

        submitted = controller.submit_assistant_reply(" ")

        self.assertFalse(submitted)
        self.assertEqual(requests, [])
        self.assertEqual(voice.state, VoiceState.IDLE)

    def test_active_voice_operation_suppresses_automatic_speech(self) -> None:
        bus, voice, controller, requests = _build(
            VoiceConfig(enabled=True, automatic_speech_enabled=True)
        )
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        submitted = controller.submit_assistant_reply("Wait until voice is idle.")

        self.assertFalse(submitted)
        self.assertEqual(requests, [])
        self.assertEqual(voice.state, VoiceState.LISTENING)

    def test_updated_config_enables_automatic_speech(self) -> None:
        _, voice, controller, requests = _build(VoiceConfig(enabled=True))
        controller.apply_config(
            VoiceConfig(enabled=True, automatic_speech_enabled=True)
        )

        submitted = controller.submit_assistant_reply("Now speak.")

        self.assertTrue(submitted)
        self.assertEqual(len(requests), 1)
        self.assertEqual(voice.state, VoiceState.THINKING)


def _build(
    config: VoiceConfig,
) -> tuple[
    EventBus,
    VoiceController,
    AssistantSpeechController,
    list[Event],
]:
    bus = EventBus()
    voice = VoiceController(bus, config)
    requests: list[Event] = []
    bus.subscribe(EventType.VOICE_SPEAK_REQUESTED, requests.append)
    controller = AssistantSpeechController(bus, voice, config)
    return bus, voice, controller, requests


if __name__ == "__main__":
    unittest.main()
