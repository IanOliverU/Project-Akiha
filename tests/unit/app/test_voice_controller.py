"""Tests for application-level voice state orchestration."""

from __future__ import annotations

import unittest

from project_akiha.app.voice_controller import VoiceController
from project_akiha.config import VoiceConfig
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState


class VoiceControllerTest(unittest.TestCase):
    """Verify voice requests publish explicit state and diagnostic events."""

    def test_disabled_voice_starts_muted(self) -> None:
        bus = EventBus()
        states = _subscribe(bus, EventType.VOICE_STATE_CHANGED)

        controller = VoiceController(bus, VoiceConfig())

        self.assertEqual(controller.state, VoiceState.MUTED)
        self.assertEqual(states[-1].payload["state"], "muted")
        self.assertEqual(states[-1].payload["reason"], "startup_disabled")

    def test_enabled_voice_starts_idle(self) -> None:
        bus = EventBus()
        states = _subscribe(bus, EventType.VOICE_STATE_CHANGED)

        controller = VoiceController(bus, VoiceConfig(enabled=True))

        self.assertEqual(controller.state, VoiceState.IDLE)
        self.assertEqual(states[-1].payload["state"], "idle")

    def test_push_to_talk_moves_through_listening_and_thinking(self) -> None:
        bus = EventBus()
        states = _subscribe(bus, EventType.VOICE_STATE_CHANGED)
        controller = VoiceController(bus, VoiceConfig(enabled=True))

        bus.publish(EventType.VOICE_LISTEN_REQUESTED)
        bus.publish(EventType.VOICE_LISTEN_STOP_REQUESTED)

        self.assertEqual(controller.state, VoiceState.THINKING)
        self.assertEqual(controller.operation, "input")
        self.assertEqual(
            [event.payload["state"] for event in states],
            ["idle", "listening", "thinking"],
        )
        self.assertEqual(states[-1].payload["operation"], "input")

    def test_listen_cancel_returns_to_idle(self) -> None:
        bus = EventBus()
        controller = VoiceController(bus, VoiceConfig(enabled=True))

        bus.publish(EventType.VOICE_LISTEN_REQUESTED)
        bus.publish(EventType.VOICE_LISTEN_CANCEL_REQUESTED)

        self.assertEqual(controller.state, VoiceState.IDLE)

    def test_duplicate_listen_while_input_active_is_idempotent(self) -> None:
        bus = EventBus()
        events = _subscribe(bus, EventType.VOICE_ERROR_OCCURRED)
        controller = VoiceController(bus, VoiceConfig(enabled=True))
        bus.publish(EventType.VOICE_LISTEN_REQUESTED, {"source": "hosted_live"})
        events.clear()

        bus.publish(EventType.VOICE_LISTEN_REQUESTED, {"source": "talk_interrupt"})

        self.assertEqual(controller.state, VoiceState.LISTENING)
        self.assertEqual(controller.operation, "input")
        self.assertFalse(
            any(event.event_type == EventType.VOICE_ERROR_OCCURRED for event in events)
        )

    def test_transcript_returns_idle_and_publishes_editable_text(self) -> None:
        bus = EventBus()
        transcripts = _subscribe(bus, EventType.VOICE_TRANSCRIPT_READY)
        controller = VoiceController(bus, VoiceConfig(enabled=True))
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)
        bus.publish(EventType.VOICE_LISTEN_STOP_REQUESTED)

        controller.publish_transcript("  おはようございます。  ", "ja")

        self.assertEqual(controller.state, VoiceState.IDLE)
        self.assertEqual(
            transcripts[-1].payload,
            {
                "text": "おはようございます。",
                "detected_language": "ja",
            },
        )

    def test_empty_transcript_publishes_error_without_chat_event(self) -> None:
        bus = EventBus()
        errors = _subscribe(bus, EventType.VOICE_ERROR_OCCURRED)
        transcripts = _subscribe(bus, EventType.VOICE_TRANSCRIPT_READY)
        controller = VoiceController(bus, VoiceConfig(enabled=True))
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)
        bus.publish(EventType.VOICE_LISTEN_STOP_REQUESTED)

        controller.publish_transcript(" ")

        self.assertEqual(controller.state, VoiceState.IDLE)
        self.assertEqual(errors[-1].payload["code"], "empty_transcript")
        self.assertEqual(transcripts, [])

    def test_transcript_publishes_only_qualitative_confidence_policy(self) -> None:
        bus = EventBus()
        transcripts = _subscribe(bus, EventType.VOICE_TRANSCRIPT_READY)
        controller = VoiceController(bus, VoiceConfig(enabled=True))
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)
        bus.publish(EventType.VOICE_LISTEN_STOP_REQUESTED)

        controller.publish_transcript(
            "Open Discord",
            "en",
            "low",
            requires_review=True,
        )

        self.assertEqual(transcripts[-1].payload["confidence_level"], "low")
        self.assertTrue(transcripts[-1].payload["requires_review"])
        self.assertNotIn("confidence", transcripts[-1].payload)

    def test_disabled_voice_rejects_listen_request_without_state_change(self) -> None:
        bus = EventBus()
        errors = _subscribe(bus, EventType.VOICE_ERROR_OCCURRED)
        controller = VoiceController(bus, VoiceConfig())

        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        self.assertEqual(controller.state, VoiceState.MUTED)
        self.assertEqual(errors[-1].payload["code"], "voice_disabled")

    def test_disabled_input_provider_rejects_listen_request(self) -> None:
        bus = EventBus()
        errors = _subscribe(bus, EventType.VOICE_ERROR_OCCURRED)
        controller = VoiceController(
            bus,
            VoiceConfig(enabled=True, input_provider="disabled"),
        )

        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        self.assertEqual(controller.state, VoiceState.IDLE)
        self.assertEqual(errors[-1].payload["code"], "input_disabled")

    def test_speech_request_moves_from_synthesis_to_playback(self) -> None:
        bus = EventBus()
        controller = VoiceController(bus, VoiceConfig(enabled=True))

        bus.publish(EventType.VOICE_SPEAK_REQUESTED, {"text": "Good morning."})
        self.assertEqual(controller.state, VoiceState.THINKING)
        self.assertEqual(controller.operation, "output")

        controller.mark_speaking()
        self.assertEqual(controller.state, VoiceState.SPEAKING)

        bus.publish(EventType.VOICE_SPEAK_STOP_REQUESTED)
        self.assertEqual(controller.state, VoiceState.IDLE)

    def test_speech_stop_does_not_cancel_active_transcription(self) -> None:
        bus = EventBus()
        controller = VoiceController(bus, VoiceConfig(enabled=True))
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)
        bus.publish(EventType.VOICE_LISTEN_STOP_REQUESTED)

        bus.publish(EventType.VOICE_SPEAK_STOP_REQUESTED)

        self.assertEqual(controller.state, VoiceState.THINKING)

    def test_speech_request_cannot_take_ownership_from_microphone(self) -> None:
        bus = EventBus()
        errors = _subscribe(bus, EventType.VOICE_ERROR_OCCURRED)
        controller = VoiceController(bus, VoiceConfig(enabled=True))
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        bus.publish(EventType.VOICE_SPEAK_REQUESTED, {"text": "Do not overlap."})

        self.assertEqual(controller.state, VoiceState.LISTENING)
        self.assertEqual(controller.operation, "input")
        self.assertEqual(errors[-1].payload["code"], "half_duplex_input_active")

    def test_speech_request_cannot_overlap_transcript_finalization(self) -> None:
        bus = EventBus()
        errors = _subscribe(bus, EventType.VOICE_ERROR_OCCURRED)
        controller = VoiceController(bus, VoiceConfig(enabled=True))
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)
        bus.publish(EventType.VOICE_LISTEN_STOP_REQUESTED)

        bus.publish(EventType.VOICE_SPEAK_REQUESTED, {"text": "Do not overlap."})

        self.assertEqual(controller.state, VoiceState.THINKING)
        self.assertEqual(controller.operation, "input")
        self.assertEqual(errors[-1].payload["code"], "half_duplex_input_active")

    def test_listen_request_cannot_take_ownership_from_speech(self) -> None:
        bus = EventBus()
        errors = _subscribe(bus, EventType.VOICE_ERROR_OCCURRED)
        controller = VoiceController(bus, VoiceConfig(enabled=True))
        bus.publish(EventType.VOICE_SPEAK_REQUESTED, {"text": "Speaking."})
        controller.mark_speaking()

        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        self.assertEqual(controller.state, VoiceState.SPEAKING)
        self.assertEqual(controller.operation, "output")
        self.assertEqual(errors[-1].payload["code"], "half_duplex_output_active")

    def test_listen_request_cannot_overlap_synthesis(self) -> None:
        bus = EventBus()
        errors = _subscribe(bus, EventType.VOICE_ERROR_OCCURRED)
        controller = VoiceController(bus, VoiceConfig(enabled=True))
        bus.publish(EventType.VOICE_SPEAK_REQUESTED, {"text": "Synthesizing."})

        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        self.assertEqual(controller.state, VoiceState.THINKING)
        self.assertEqual(controller.operation, "output")
        self.assertEqual(errors[-1].payload["code"], "half_duplex_output_active")

    def test_listen_cancel_does_not_cancel_active_synthesis(self) -> None:
        bus = EventBus()
        controller = VoiceController(bus, VoiceConfig(enabled=True))
        bus.publish(EventType.VOICE_SPEAK_REQUESTED, {"text": "Test"})

        bus.publish(EventType.VOICE_LISTEN_CANCEL_REQUESTED)

        self.assertEqual(controller.state, VoiceState.THINKING)

    def test_invalid_speech_request_does_not_start_synthesis(self) -> None:
        bus = EventBus()
        errors = _subscribe(bus, EventType.VOICE_ERROR_OCCURRED)
        controller = VoiceController(bus, VoiceConfig(enabled=True))

        bus.publish(EventType.VOICE_SPEAK_REQUESTED, {"text": " "})

        self.assertEqual(controller.state, VoiceState.IDLE)
        self.assertEqual(errors[-1].payload["code"], "invalid_speech_request")

    def test_unexpected_playback_does_not_interrupt_listening(self) -> None:
        bus = EventBus()
        errors = _subscribe(bus, EventType.VOICE_ERROR_OCCURRED)
        controller = VoiceController(bus, VoiceConfig(enabled=True))
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        controller.mark_speaking()

        self.assertEqual(controller.state, VoiceState.LISTENING)
        self.assertEqual(errors[-1].payload["code"], "unexpected_playback")

    def test_apply_config_enables_voice_without_restart(self) -> None:
        bus = EventBus()
        controller = VoiceController(bus, VoiceConfig())

        controller.apply_config(VoiceConfig(enabled=True))

        self.assertTrue(controller.config.enabled)
        self.assertEqual(controller.state, VoiceState.IDLE)

    def test_disabling_input_during_listening_returns_idle(self) -> None:
        bus = EventBus()
        controller = VoiceController(bus, VoiceConfig(enabled=True))
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        controller.apply_config(VoiceConfig(enabled=True, input_provider="disabled"))

        self.assertEqual(controller.state, VoiceState.IDLE)

    def test_disabling_output_during_playback_returns_idle(self) -> None:
        bus = EventBus()
        controller = VoiceController(bus, VoiceConfig(enabled=True))
        bus.publish(EventType.VOICE_SPEAK_REQUESTED, {"text": "Test"})
        controller.mark_speaking()

        controller.apply_config(VoiceConfig(enabled=True, output_provider="disabled"))

        self.assertEqual(controller.state, VoiceState.IDLE)

    def test_unexpected_transcript_is_rejected_without_exposing_text(self) -> None:
        bus = EventBus()
        errors = _subscribe(bus, EventType.VOICE_ERROR_OCCURRED)
        transcripts = _subscribe(bus, EventType.VOICE_TRANSCRIPT_READY)
        controller = VoiceController(bus, VoiceConfig(enabled=True))

        controller.publish_transcript("Private late transcript")

        self.assertEqual(errors[-1].payload["code"], "unexpected_transcript")
        self.assertNotIn("Private late transcript", errors[-1].payload.values())
        self.assertEqual(transcripts, [])

    def test_report_error_publishes_transient_error_and_recovers(self) -> None:
        bus = EventBus()
        errors = _subscribe(bus, EventType.VOICE_ERROR_OCCURRED)
        states = _subscribe(bus, EventType.VOICE_STATE_CHANGED)
        controller = VoiceController(bus, VoiceConfig(enabled=True))

        controller.report_error("provider_unavailable", "Provider unavailable.")

        self.assertEqual(controller.state, VoiceState.IDLE)
        self.assertEqual(errors[-1].payload["code"], "provider_unavailable")
        self.assertEqual(
            [event.payload["state"] for event in states[-2:]],
            ["error", "idle"],
        )

    def test_notify_error_does_not_interrupt_active_voice(self) -> None:
        bus = EventBus()
        errors = _subscribe(bus, EventType.VOICE_ERROR_OCCURRED)
        controller = VoiceController(bus, VoiceConfig(enabled=True))
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        controller.notify_error("action_rejected", "Action rejected.")

        self.assertEqual(controller.state, VoiceState.LISTENING)
        self.assertEqual(errors[-1].payload["code"], "action_rejected")


def _subscribe(bus: EventBus, event_type: EventType) -> list[Event]:
    events: list[Event] = []
    bus.subscribe(event_type, events.append)
    return events


if __name__ == "__main__":
    unittest.main()
