"""Tests for automatic assistant-reply speech policy."""

from __future__ import annotations

import unittest

from project_akiha.app.assistant_speech_controller import AssistantSpeechController
from project_akiha.app.voice_controller import VoiceController
from project_akiha.config import VoiceConfig
from project_akiha.core.behavior import CompanionMood
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState
from project_akiha.services.speech_identity import StyledSpeech


class AssistantSpeechControllerTest(unittest.TestCase):
    """Verify only completed, permitted replies enter synthesis."""

    def test_enabled_automatic_speech_publishes_exact_assistant_text(self) -> None:
        bus, voice, controller, requests = _build(
            VoiceConfig(enabled=True, automatic_speech_enabled=True)
        )
        response = "  A completed assistant response.  "

        submitted = controller.submit_assistant_reply(response)

        self.assertTrue(submitted)
        self.assertEqual(requests[-1].payload["text"], response.strip())
        self.assertEqual(requests[-1].payload["source"], "assistant_reply")
        self.assertEqual(requests[-1].payload["speaking_rate_multiplier"], 1.0)
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

    def test_styles_only_spoken_copy_and_passes_current_mood(self) -> None:
        config = VoiceConfig(enabled=True, automatic_speech_enabled=True)
        bus = EventBus()
        voice = VoiceController(bus, config)
        requests: list[Event] = []
        bus.subscribe(EventType.VOICE_SPEAK_REQUESTED, requests.append)
        moods: list[CompanionMood | None] = []

        class StyleService:
            def style(
                self,
                text: str,
                mood: CompanionMood | None = None,
            ) -> StyledSpeech:
                moods.append(mood)
                return StyledSpeech("承知しました。", 0.94)

        controller = AssistantSpeechController(
            bus,
            voice,
            config,
            style_service=StyleService(),
            mood_provider=lambda: CompanionMood.RESTING,
        )
        displayed_response = "**Understood.**"

        submitted = controller.submit_assistant_reply(displayed_response)

        self.assertTrue(submitted)
        self.assertEqual(displayed_response, "**Understood.**")
        self.assertEqual(requests[-1].payload["text"], "承知しました。")
        self.assertEqual(requests[-1].payload["speaking_rate_multiplier"], 0.94)
        self.assertEqual(moods, [CompanionMood.RESTING])

    def test_style_exception_falls_back_without_logging_reply_content(self) -> None:
        config = VoiceConfig(enabled=True, automatic_speech_enabled=True)
        bus = EventBus()
        voice = VoiceController(bus, config)
        requests: list[Event] = []
        bus.subscribe(EventType.VOICE_SPEAK_REQUESTED, requests.append)

        class FailingStyleService:
            def style(
                self,
                text: str,
                mood: CompanionMood | None = None,
            ) -> StyledSpeech:
                del text, mood
                raise RuntimeError("private response must not be logged")

        controller = AssistantSpeechController(
            bus,
            voice,
            config,
            style_service=FailingStyleService(),
        )

        with self.assertLogs("project_akiha.voice.identity", "WARNING") as logs:
            submitted = controller.submit_assistant_reply("Private response.")

        self.assertTrue(submitted)
        self.assertEqual(requests[-1].payload["text"], "Private response.")
        self.assertNotIn("Private response", " ".join(logs.output))
        self.assertNotIn("must not be logged", " ".join(logs.output))

    def test_malformed_style_result_falls_back_to_raw_reply(self) -> None:
        config = VoiceConfig(enabled=True, automatic_speech_enabled=True)
        bus = EventBus()
        voice = VoiceController(bus, config)
        requests: list[Event] = []
        bus.subscribe(EventType.VOICE_SPEAK_REQUESTED, requests.append)

        class EmptyStyleService:
            def style(
                self,
                text: str,
                mood: CompanionMood | None = None,
            ) -> StyledSpeech:
                del text, mood
                return StyledSpeech(" ")

        controller = AssistantSpeechController(
            bus,
            voice,
            config,
            style_service=EmptyStyleService(),
        )

        with self.assertLogs("project_akiha.voice.identity", "WARNING"):
            submitted = controller.submit_assistant_reply("Fallback reply.")

        self.assertTrue(submitted)
        self.assertEqual(requests[-1].payload["text"], "Fallback reply.")


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
