"""Tests for controlled Talk-to-interrupt orchestration."""

from __future__ import annotations

import unittest

from project_akiha.app.talk_interruption_controller import (
    TalkInterruptionController,
)
from project_akiha.app.voice_controller import VoiceController
from project_akiha.config import VoiceConfig
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState


class TalkInterruptionControllerTest(unittest.TestCase):
    def test_idle_talk_requests_listening_without_cancellation(self) -> None:
        context = _build()

        result = context.controller.request_talk()

        self.assertFalse(result.output_stopped)
        self.assertFalse(result.work_cancelled)
        self.assertTrue(result.listening_requested)
        self.assertEqual(context.voice.state, VoiceState.LISTENING)
        self.assertEqual(context.callbacks, [])
        self.assertEqual(context.events, ["listen"])

    def test_talk_stops_output_then_cancels_work_before_listening(self) -> None:
        context = _build(has_work=True)
        context.bus.publish(EventType.VOICE_SPEAK_REQUESTED, {"text": "Hello."})
        context.voice.mark_speaking()
        context.events.clear()

        result = context.controller.request_talk()

        self.assertTrue(result.output_stopped)
        self.assertTrue(result.work_cancelled)
        self.assertTrue(result.listening_requested)
        self.assertEqual(context.events, ["stop", "cancel", "listen"])
        self.assertEqual(context.callbacks, ["cancel"])
        self.assertEqual(context.voice.state, VoiceState.LISTENING)
        self.assertEqual(context.voice.operation, "input")

    def test_talk_cancels_generation_before_output_has_started(self) -> None:
        context = _build(has_work=True)

        result = context.controller.request_talk()

        self.assertFalse(result.output_stopped)
        self.assertTrue(result.work_cancelled)
        self.assertEqual(context.events, ["cancel", "listen"])
        self.assertEqual(context.voice.state, VoiceState.LISTENING)

    def test_talk_stops_synthesis_before_requesting_listening(self) -> None:
        context = _build()
        context.bus.publish(EventType.VOICE_SPEAK_REQUESTED, {"text": "Hello."})
        context.events.clear()

        result = context.controller.request_talk()

        self.assertTrue(result.output_stopped)
        self.assertFalse(result.work_cancelled)
        self.assertEqual(context.events, ["stop", "listen"])
        self.assertEqual(context.voice.state, VoiceState.LISTENING)

    def test_unavailable_input_does_not_interrupt_current_output(self) -> None:
        context = _build(input_provider="disabled", has_work=True)
        context.bus.publish(EventType.VOICE_SPEAK_REQUESTED, {"text": "Hello."})
        context.voice.mark_speaking()
        context.events.clear()

        result = context.controller.request_talk()

        self.assertFalse(result.output_stopped)
        self.assertFalse(result.work_cancelled)
        self.assertFalse(result.listening_requested)
        self.assertEqual(context.callbacks, [])
        self.assertEqual(context.events, ["listen"])
        self.assertEqual(context.voice.state, VoiceState.SPEAKING)
        self.assertEqual(context.voice.operation, "output")

    def test_disabled_push_to_talk_preserves_current_output(self) -> None:
        context = _build(push_to_talk_enabled=False, has_work=True)
        context.bus.publish(EventType.VOICE_SPEAK_REQUESTED, {"text": "Hello."})
        context.events.clear()

        result = context.controller.request_talk()

        self.assertFalse(result.output_stopped)
        self.assertFalse(result.work_cancelled)
        self.assertFalse(result.listening_requested)
        self.assertEqual(context.events, ["listen"])
        self.assertEqual(context.voice.operation, "output")


class _Context:
    def __init__(
        self,
        *,
        bus: EventBus,
        voice: VoiceController,
        controller: TalkInterruptionController,
        callbacks: list[str],
        events: list[str],
    ) -> None:
        self.bus = bus
        self.voice = voice
        self.controller = controller
        self.callbacks = callbacks
        self.events = events


def _build(
    *,
    input_provider: str = "faster-whisper",
    push_to_talk_enabled: bool = True,
    has_work: bool = False,
) -> _Context:
    bus = EventBus()
    voice = VoiceController(
        bus,
        VoiceConfig(
            enabled=True,
            input_provider=input_provider,
            push_to_talk_enabled=push_to_talk_enabled,
        ),
    )
    callbacks: list[str] = []
    events: list[str] = []

    def record_stop(event: Event) -> None:
        source = event.payload.get("reason")
        if source == "talk_interrupt":
            events.append("stop")

    def record_listen(event: Event) -> None:
        source = event.payload.get("source")
        if source == "talk_interrupt":
            events.append("listen")

    def cancel_work() -> None:
        callbacks.append("cancel")
        events.append("cancel")

    bus.subscribe(EventType.VOICE_SPEAK_STOP_REQUESTED, record_stop)
    bus.subscribe(EventType.VOICE_LISTEN_REQUESTED, record_listen)
    controller = TalkInterruptionController(
        event_bus=bus,
        voice_controller=voice,
        has_interruptible_work=lambda: has_work,
        cancel_interruptible_work=cancel_work,
    )
    return _Context(
        bus=bus,
        voice=voice,
        controller=controller,
        callbacks=callbacks,
        events=events,
    )
