"""Tests for explicit local conversation-session lifecycle ownership."""

from __future__ import annotations

import unittest
from collections.abc import Callable
from time import monotonic

from project_akiha.app.local_conversation_session_controller import (
    LocalConversationSessionController,
)
from project_akiha.app.push_to_talk_session_controller import (
    PushToTalkSessionController,
)
from project_akiha.app.voice_controller import VoiceController
from project_akiha.app.voice_session_coordinator import VoiceSessionCoordinator
from project_akiha.config import VoiceConfig
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState
from project_akiha.core.voice_session import (
    SessionLifecycle,
    VoiceInputMode,
    VoiceProcessingMode,
)


class LocalConversationSessionControllerTest(unittest.TestCase):
    def test_construction_never_starts_microphone_or_session(self) -> None:
        context = _build()

        self.assertFalse(context.controller.active)
        self.assertEqual(context.coordinator.snapshot.lifecycle, SessionLifecycle.IDLE)
        self.assertEqual(context.voice.state, VoiceState.IDLE)
        self.assertEqual(context.states, [])

    def test_explicit_start_opens_first_persistent_local_turn(self) -> None:
        context = _build()

        self.assertTrue(context.controller.start())

        snapshot = context.coordinator.snapshot
        turn = snapshot.active_turn
        assert turn is not None
        self.assertTrue(context.controller.active)
        self.assertEqual(snapshot.lifecycle, SessionLifecycle.ACTIVE)
        self.assertEqual(snapshot.processing_mode, VoiceProcessingMode.LOCAL_MODULAR)
        self.assertEqual(turn.input_mode, VoiceInputMode.LOCAL_CONVERSATION)
        self.assertEqual(context.voice.state, VoiceState.LISTENING)
        self.assertEqual(context.states, [True])

    def test_end_cancels_input_work_and_returns_to_idle(self) -> None:
        context = _build()
        context.controller.start()

        self.assertTrue(context.controller.end())

        self.assertFalse(context.controller.active)
        self.assertEqual(context.coordinator.snapshot.lifecycle, SessionLifecycle.IDLE)
        self.assertEqual(context.voice.state, VoiceState.IDLE)
        self.assertEqual(context.cancelled_work, [True])
        self.assertEqual(context.states, [True, False])

    def test_unavailable_input_rejects_start_without_cancelling_work(self) -> None:
        context = _build(voice_config=VoiceConfig())

        self.assertFalse(context.controller.start())

        self.assertFalse(context.controller.active)
        self.assertEqual(context.coordinator.snapshot.lifecycle, SessionLifecycle.IDLE)
        self.assertEqual(
            context.errors[-1].payload["code"], "conversation_input_unavailable"
        )
        self.assertEqual(context.cancelled_work, [])

    def test_repeated_start_and_end_are_idempotent(self) -> None:
        context = _build()

        self.assertTrue(context.controller.start())
        self.assertFalse(context.controller.start())
        self.assertTrue(context.controller.end())
        self.assertFalse(context.controller.end())

        self.assertEqual(context.states, [True, False])
        self.assertEqual(context.cancelled_work, [True])

    def test_session_error_deactivates_explicit_conversation(self) -> None:
        context = _build()
        context.controller.start()

        context.coordinator.report_error("capture_failed")

        self.assertFalse(context.controller.active)
        self.assertEqual(context.states, [True, False])

    def test_completed_assistant_playback_reopens_microphone_once(self) -> None:
        context = _build()
        context.controller.start()
        context.bus.publish(EventType.VOICE_LISTEN_STOP_REQUESTED)
        context.voice.publish_transcript("Hello Akiha", "en", "high")

        context.bus.publish(
            EventType.VOICE_RESPONSE_PLAYBACK_COMPLETED,
            {"source": "assistant_reply", "delivery": "streaming"},
        )
        context.bus.publish(
            EventType.VOICE_RESPONSE_PLAYBACK_COMPLETED,
            {"source": "assistant_reply", "delivery": "streaming"},
        )

        snapshot = context.coordinator.snapshot
        turn = snapshot.active_turn
        assert turn is not None
        self.assertEqual(turn.input_mode, VoiceInputMode.LOCAL_CONVERSATION)
        self.assertEqual(context.voice.state, VoiceState.LISTENING)

    def test_non_assistant_playback_never_reopens_microphone(self) -> None:
        context = _build()
        context.controller.start()
        context.bus.publish(EventType.VOICE_LISTEN_STOP_REQUESTED)
        context.voice.publish_transcript("Hello Akiha", "en", "high")

        context.bus.publish(
            EventType.VOICE_RESPONSE_PLAYBACK_COMPLETED,
            {"source": "replay", "delivery": "fallback"},
        )

        self.assertIsNone(context.coordinator.snapshot.active_turn)
        self.assertEqual(context.voice.state, VoiceState.IDLE)

    def test_inactive_session_ignores_assistant_playback_completion(self) -> None:
        context = _build()

        context.bus.publish(
            EventType.VOICE_RESPONSE_PLAYBACK_COMPLETED,
            {"source": "assistant_reply", "delivery": "streaming"},
        )

        self.assertEqual(context.coordinator.snapshot.lifecycle, SessionLifecycle.IDLE)
        self.assertEqual(context.voice.state, VoiceState.IDLE)

    def test_unfinished_work_blocks_automatic_microphone_reopen(self) -> None:
        work_active = [False]
        context = _build(has_work=lambda: work_active[0])
        context.controller.start()
        context.bus.publish(EventType.VOICE_LISTEN_STOP_REQUESTED)
        context.voice.publish_transcript("Hello Akiha", "en", "high")
        work_active[0] = True

        context.bus.publish(
            EventType.VOICE_RESPONSE_PLAYBACK_COMPLETED,
            {"source": "assistant_reply", "delivery": "streaming"},
        )

        self.assertIsNone(context.coordinator.snapshot.active_turn)
        self.assertEqual(context.voice.state, VoiceState.IDLE)

    def test_unfinished_work_blocks_explicit_session_start(self) -> None:
        context = _build(has_work=lambda: True)

        self.assertFalse(context.controller.start())

        self.assertEqual(context.coordinator.snapshot.lifecycle, SessionLifecycle.IDLE)
        self.assertEqual(
            context.errors[-1].payload["code"],
            "conversation_session_busy",
        )

    def test_tick_publishes_monotonic_elapsed_state(self) -> None:
        clock = _FakeClock()
        context = _build(clock=clock)
        context.controller.start()

        clock.advance(65.9)
        context.controller.tick()

        state = context.state_events[-1]
        self.assertTrue(state.payload["active"])
        self.assertEqual(state.payload["mode"], "local")
        self.assertEqual(state.payload["elapsed_seconds"], 65)
        self.assertEqual(state.payload["idle_seconds"], 65)
        self.assertEqual(state.payload["reason"], "")

    def test_idle_timeout_ends_and_releases_active_capture(self) -> None:
        clock = _FakeClock()
        context = _build(
            clock=clock,
            voice_config=VoiceConfig(
                enabled=True,
                local_conversation_idle_timeout_seconds=15,
            ),
        )
        context.controller.start()

        clock.advance(15)
        context.controller.tick()

        self.assertFalse(context.controller.active)
        self.assertEqual(context.voice.state, VoiceState.IDLE)
        self.assertEqual(context.coordinator.snapshot.lifecycle, SessionLifecycle.IDLE)
        self.assertEqual(context.state_events[-1].payload["reason"], "idle_timeout")

    def test_session_limit_ends_even_when_idle_time_was_reset(self) -> None:
        clock = _FakeClock()
        context = _build(
            clock=clock,
            voice_config=VoiceConfig(
                enabled=True,
                local_conversation_idle_timeout_seconds=120,
                local_conversation_max_duration_seconds=60,
            ),
        )
        context.controller.start()
        clock.advance(50)
        context.voice.publish_transcript("Still here", "en", "high")

        clock.advance(10)
        context.controller.tick()

        self.assertFalse(context.controller.active)
        self.assertEqual(context.state_events[-1].payload["reason"], "session_timeout")

    def test_final_transcript_resets_idle_time_without_resetting_elapsed(self) -> None:
        clock = _FakeClock()
        context = _build(
            clock=clock,
            voice_config=VoiceConfig(
                enabled=True,
                local_conversation_idle_timeout_seconds=15,
            ),
        )
        context.controller.start()
        clock.advance(10)

        context.voice.publish_transcript("Hello", "en", "high")
        clock.advance(10)
        context.controller.tick()

        self.assertTrue(context.controller.active)
        self.assertEqual(context.state_events[-1].payload["elapsed_seconds"], 20)
        self.assertEqual(context.state_events[-1].payload["idle_seconds"], 10)


class _Context:
    def __init__(
        self,
        *,
        bus: EventBus,
        voice: VoiceController,
        coordinator: VoiceSessionCoordinator,
        controller: LocalConversationSessionController,
        states: list[bool],
        state_events: list[Event],
        errors: list[Event],
        cancelled_work: list[bool],
    ) -> None:
        self.bus = bus
        self.voice = voice
        self.coordinator = coordinator
        self.controller = controller
        self.states = states
        self.state_events = state_events
        self.errors = errors
        self.cancelled_work = cancelled_work


def _build(
    *,
    voice_config: VoiceConfig | None = None,
    has_work: Callable[[], bool] = lambda: False,
    clock: Callable[[], float] | None = None,
) -> _Context:
    bus = EventBus()
    voice = VoiceController(bus, voice_config or VoiceConfig(enabled=True))
    coordinator = VoiceSessionCoordinator(session_id_factory=lambda: "session-1")
    PushToTalkSessionController(
        event_bus=bus,
        voice_controller=voice,
        session_coordinator=coordinator,
        processing_mode_provider=lambda: VoiceProcessingMode.LOCAL_MODULAR,
        input_provider_name=lambda: "faster-whisper",
    )
    states: list[bool] = []
    state_events: list[Event] = []
    errors: list[Event] = []
    cancelled_work: list[bool] = []

    def observe_state(event: Event) -> None:
        states.append(event.payload.get("active") is True)
        state_events.append(event)

    bus.subscribe(EventType.VOICE_CONVERSATION_STATE_CHANGED, observe_state)
    bus.subscribe(EventType.VOICE_ERROR_OCCURRED, errors.append)
    controller = LocalConversationSessionController(
        event_bus=bus,
        voice_controller=voice,
        session_coordinator=coordinator,
        processing_mode_provider=lambda: VoiceProcessingMode.LOCAL_MODULAR,
        has_interruptible_work=has_work,
        cancel_interruptible_work=lambda: cancelled_work.append(True),
        monotonic_clock=clock or monotonic,
    )
    return _Context(
        bus=bus,
        voice=voice,
        coordinator=coordinator,
        controller=controller,
        states=states,
        state_events=state_events,
        errors=errors,
        cancelled_work=cancelled_work,
    )


class _FakeClock:
    def __init__(self) -> None:
        self._now = 100.0

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds
