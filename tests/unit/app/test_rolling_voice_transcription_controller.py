"""Tests for the production rolling voice-controller handoff."""

from __future__ import annotations

import unittest
from collections.abc import Callable

from project_akiha.app.push_to_talk_session_controller import (
    PushToTalkSessionController,
)
from project_akiha.app.rolling_voice_transcription_controller import (
    RollingVoiceTranscriptionController,
)
from project_akiha.app.voice_controller import VoiceController
from project_akiha.app.voice_session_coordinator import VoiceSessionCoordinator
from project_akiha.config import VoiceConfig
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.voice_session import (
    EndpointReason,
    SessionLifecycle,
    TranscriptConfidence,
    TranscriptRevision,
    TranscriptStatus,
    VoiceProcessingMode,
)
from project_akiha.providers.voice import CapturedAudio


class RollingVoiceTranscriptionControllerTest(unittest.TestCase):
    def test_queues_appended_frames_while_one_worker_is_active(self) -> None:
        context = _build()
        context.bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        context.controller.submit_partial(_audio(bytes(3_200)))
        context.controller.submit_partial(_audio(bytes(6_400)))

        self.assertEqual(len(context.threads), 1)
        self.assertEqual(len(context.threads[0].frames), 1)
        context.threads[0].finished.emit()
        self.assertEqual(len(context.threads), 2)
        self.assertEqual(len(context.threads[1].frames), 1)
        self.assertEqual(context.threads[1].frames[0].sequence_number, 1)

    def test_final_waits_behind_partial_and_keeps_silence_reason(self) -> None:
        context = _build()
        context.bus.publish(EventType.VOICE_LISTEN_REQUESTED)
        context.controller.submit_partial(_audio(bytes(3_200)))

        context.bus.publish(
            EventType.VOICE_LISTEN_STOP_REQUESTED,
            {"reason": "silence_detected"},
        )
        context.controller.submit(_audio(bytes(4_000)))

        self.assertEqual(len(context.threads), 1)
        context.threads[0].finished.emit()
        self.assertEqual(len(context.threads), 2)
        self.assertEqual(context.threads[1].endpoint_reason, EndpointReason.SILENCE)
        self.assertEqual(len(context.threads[1].frames), 1)

    def test_canonical_revisions_preserve_preview_and_review_gate(self) -> None:
        context = _build()
        ready: list[Event] = []
        partials: list[Event] = []
        context.bus.subscribe(EventType.VOICE_TRANSCRIPT_READY, ready.append)
        context.bus.subscribe(EventType.VOICE_TRANSCRIPT_PARTIAL, partials.append)
        context.bus.publish(EventType.VOICE_LISTEN_REQUESTED)
        turn = context.coordinator.snapshot.active_turn
        assert turn is not None
        partial = _revision(turn.session_id, turn.turn_id, 0, is_final=False)

        context.relay.revision_ready.emit(partial)

        active = context.coordinator.snapshot.active_turn
        assert active is not None
        self.assertEqual(active.latest_transcript_revision, 0)
        self.assertIs(partials[-1].payload["revision"], partial)

        context.bus.publish(
            EventType.VOICE_LISTEN_STOP_REQUESTED,
            {"reason": "silence_detected"},
        )
        final = _revision(
            turn.session_id,
            turn.turn_id,
            1,
            is_final=True,
            confidence=TranscriptConfidence.LOW,
        )
        context.relay.revision_ready.emit(final)

        self.assertEqual(context.coordinator.snapshot.lifecycle, SessionLifecycle.IDLE)
        self.assertIs(ready[-1].payload["revision"], final)
        self.assertTrue(ready[-1].payload["requires_review"])
        self.assertEqual(ready[-1].payload["confidence_level"], "low")

    def test_stale_revision_is_discarded_before_public_event(self) -> None:
        context = _build()
        partials: list[Event] = []
        context.bus.subscribe(EventType.VOICE_TRANSCRIPT_PARTIAL, partials.append)
        context.bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        context.relay.revision_ready.emit(
            _revision("other-session", "1", 0, is_final=False)
        )

        self.assertEqual(partials, [])

    def test_microphone_test_remains_on_batch_diagnostic_path(self) -> None:
        context = _build()
        context.bus.publish(
            EventType.VOICE_LISTEN_REQUESTED,
            {"source": "settings_microphone_test"},
        )
        audio = _audio(bytes(3_200))

        context.controller.submit_test(audio)

        self.assertEqual(context.diagnostic.test_audio, [audio])
        self.assertEqual(context.threads, [])

    def test_cancel_releases_worker_pending_audio_and_diagnostics(self) -> None:
        context = _build()
        context.bus.publish(EventType.VOICE_LISTEN_REQUESTED)
        context.controller.submit_partial(_audio(bytes(3_200)))
        context.controller.submit_partial(_audio(bytes(6_400)))

        context.controller.cancel(wait_ms=25)

        self.assertTrue(context.threads[0].cancelled)
        self.assertEqual(context.threads[0].wait_ms, 25)
        self.assertEqual(context.diagnostic.cancel_waits, [25])


class _Context:
    def __init__(self) -> None:
        self.bus = EventBus()
        self.config = VoiceConfig(
            enabled=True,
            live_transcription_enabled=True,
            capture_timeout_seconds=30,
        )
        self.voice = VoiceController(self.bus, self.config)
        self.coordinator = VoiceSessionCoordinator(
            session_id_factory=lambda: "session-1"
        )
        PushToTalkSessionController(
            self.bus,
            self.voice,
            self.coordinator,
            processing_mode_provider=lambda: VoiceProcessingMode.LOCAL_MODULAR,
            input_provider_name=lambda: "faster-whisper",
        )
        self.diagnostic = _DiagnosticController()
        self.threads: list[_Thread] = []
        self.relay = _Relay()

        def thread_factory(recognizer, frames, endpoint_reason):
            del recognizer
            thread = _Thread(frames, endpoint_reason)
            self.threads.append(thread)
            return thread

        self.controller = RollingVoiceTranscriptionController(
            self.bus,
            self.voice,
            self.coordinator,
            service=object(),  # type: ignore[arg-type]
            config=self.config,
            diagnostic_controller=self.diagnostic,  # type: ignore[arg-type]
            thread_factory=thread_factory,
            relay_factory=lambda: self.relay,
        )


class _Signal:
    def __init__(self) -> None:
        self.handlers: list[Callable[..., None]] = []

    def connect(self, handler: Callable[..., None]) -> None:
        self.handlers.append(handler)

    def emit(self, *args: object) -> None:
        for handler in tuple(self.handlers):
            handler(*args)


class _Relay:
    def __init__(self) -> None:
        self.revision_ready = _Signal()


class _Thread:
    def __init__(self, frames, endpoint_reason) -> None:
        self.recognition_failed = _Signal()
        self.recognition_cancelled = _Signal()
        self.finished = _Signal()
        self.frames = frames
        self.endpoint_reason = endpoint_reason
        self.is_finalizing = endpoint_reason is not None
        self.started = False
        self.cancelled = False
        self.wait_ms = 0

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True

    def wait(self, time: int = 0) -> bool:
        self.wait_ms = time
        return True


class _DiagnosticController:
    def __init__(self) -> None:
        self.test_audio: list[CapturedAudio] = []
        self.cancel_waits: list[int] = []

    def apply_service(self, service: object) -> None:
        del service

    def submit_test(self, audio: CapturedAudio) -> None:
        self.test_audio.append(audio)

    def cancel(self, wait_ms: int = 2_000) -> None:
        self.cancel_waits.append(wait_ms)


def _build() -> _Context:
    return _Context()


def _audio(data: bytes) -> CapturedAudio:
    return CapturedAudio(data=data, sample_rate_hz=16_000)


def _revision(
    session_id: str,
    turn_id: str,
    revision_number: int,
    *,
    is_final: bool,
    confidence: TranscriptConfidence = TranscriptConfidence.HIGH,
) -> TranscriptRevision:
    return TranscriptRevision(
        session_id=session_id,
        turn_id=turn_id,
        revision_number=revision_number,
        text="Open Spotify" if is_final else "Open",
        status=TranscriptStatus.FINAL if is_final else TranscriptStatus.PARTIAL,
        provider_name="faster-whisper",
        detected_language="en",
        confidence=confidence,
        endpoint_reason=EndpointReason.SILENCE if is_final else None,
    )


if __name__ == "__main__":
    unittest.main()
