"""Coordinate local speech recognition workers."""

from __future__ import annotations

from collections.abc import Callable
from difflib import SequenceMatcher
from typing import Protocol

from project_akiha.app.voice_controller import VoiceController
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState
from project_akiha.providers.voice import CapturedAudio, VoiceTranscript
from project_akiha.services.speech_input import SpeechInputService
from project_akiha.services.voice_confidence import (
    transcript_requires_review,
    voice_confidence_level,
)
from project_akiha.ui.voice_transcription_worker import VoiceTranscriptionThread


class _TranscriptionThread(Protocol):
    transcript_ready: object
    transcription_failed: object
    transcription_cancelled: object
    finished: object

    def start(self) -> None:
        """Start transcription."""

    def cancel(self) -> None:
        """Request cancellation."""

    def wait(self, time: int = ...) -> bool:
        """Wait for completion."""


class _PartialTranscriptStabilizer:
    """Keep cumulative STT previews responsive without visible regressions."""

    def __init__(self) -> None:
        self._presented = ""
        self._pending_revision = ""

    def reset(self) -> None:
        """Forget preview state at the boundary of one recording."""
        self._presented = ""
        self._pending_revision = ""

    def observe(self, text: str) -> str | None:
        """Return a safe preview update, or suppress an unstable revision."""
        candidate = " ".join(text.split())
        if not candidate:
            return None
        if not self._presented:
            return self._accept(candidate)

        presented_key = self._presented.casefold()
        candidate_key = candidate.casefold()
        if candidate_key == presented_key:
            self._pending_revision = ""
            return None
        if presented_key.startswith(candidate_key):
            self._pending_revision = ""
            return None
        if _is_related_growth(presented_key, candidate_key):
            return self._accept(candidate)

        if self._pending_revision and (
            candidate_key == self._pending_revision.casefold()
            or _is_related_growth(
                self._pending_revision.casefold(),
                candidate_key,
            )
        ):
            return self._accept(candidate)

        self._pending_revision = candidate
        return None

    def _accept(self, text: str) -> str:
        self._presented = text
        self._pending_revision = ""
        return text


class VoiceTranscriptionController:
    """Run at most one STT worker and return editable transcript text."""

    def __init__(
        self,
        event_bus: EventBus,
        voice_controller: VoiceController,
        service: SpeechInputService,
        *,
        thread_factory: Callable[
            [SpeechInputService, CapturedAudio],
            _TranscriptionThread,
        ] = VoiceTranscriptionThread,
    ) -> None:
        self._event_bus = event_bus
        self._voice_controller = voice_controller
        self._service = service
        self._thread_factory = thread_factory
        self._active_threads: list[_TranscriptionThread] = []
        self._cancelled_threads: list[_TranscriptionThread] = []
        self._thread_modes: dict[_TranscriptionThread, str] = {}
        self._pending_partial: CapturedAudio | None = None
        self._pending_final: CapturedAudio | None = None
        self._partial_stabilizer = _PartialTranscriptStabilizer()

        event_bus.subscribe(
            EventType.VOICE_LISTEN_CANCEL_REQUESTED,
            self._handle_cancel_requested,
        )
        event_bus.subscribe(
            EventType.VOICE_LISTEN_REQUESTED,
            self._handle_listen_requested,
        )

    def apply_service(self, service: SpeechInputService) -> None:
        """Use an updated provider for the next recording."""
        self._service = service

    def submit(self, audio: CapturedAudio) -> None:
        """Start non-blocking transcription for captured PCM."""
        self._partial_stabilizer.reset()
        if self._active_threads:
            if all(
                self._thread_modes.get(thread) == "partial"
                for thread in self._active_threads
            ):
                self._pending_partial = None
                self._pending_final = audio
                for thread in tuple(self._active_threads):
                    thread.cancel()
                    if thread not in self._cancelled_threads:
                        self._cancelled_threads.append(thread)
                return
            self._voice_controller.report_error(
                "transcription_busy",
                "Speech recognition is already processing a recording.",
            )
            return

        self._start_thread(audio, mode="final")

    def submit_partial(self, audio: CapturedAudio) -> None:
        """Transcribe the latest live snapshot without changing voice state."""
        if (
            self._voice_controller.state != VoiceState.LISTENING
            or self._voice_controller.operation != "input"
        ):
            return
        if self._active_threads:
            if any(
                self._thread_modes.get(thread) == "final"
                for thread in self._active_threads
            ):
                return
            self._pending_partial = audio
            return
        self._start_thread(audio, mode="partial")

    def submit_test(self, audio: CapturedAudio) -> None:
        """Transcribe diagnostic audio without publishing recognized text."""
        if self._active_threads:
            self._voice_controller.report_error(
                "transcription_busy",
                "Speech recognition is already processing a recording.",
            )
            return
        self._start_thread(audio, mode="test")

    def _start_thread(self, audio: CapturedAudio, *, mode: str) -> None:
        thread = self._thread_factory(self._service, audio)
        thread.transcript_ready.connect(
            lambda transcript, worker=thread: self._handle_transcript_ready(
                worker,
                transcript,
            )
        )
        thread.transcription_failed.connect(
            lambda code, message, worker=thread: self._handle_failure(
                worker,
                code,
                message,
            )
        )
        thread.transcription_cancelled.connect(
            lambda worker=thread: self._handle_cancelled(worker)
        )
        thread.finished.connect(lambda worker=thread: self._remove_thread(worker))
        self._active_threads.append(thread)
        self._thread_modes[thread] = mode
        thread.start()

    def cancel(self, wait_ms: int = 2000) -> None:
        """Cancel active transcription and optionally wait during shutdown."""
        self._partial_stabilizer.reset()
        self._pending_partial = None
        self._pending_final = None
        unfinished = 0
        for thread in tuple(self._active_threads):
            thread.cancel()
            if thread not in self._cancelled_threads:
                self._cancelled_threads.append(thread)
            if wait_ms > 0 and not thread.wait(wait_ms):
                unfinished += 1
        if unfinished:
            raise RuntimeError(
                f"{unfinished} voice transcription worker(s) did not stop."
            )

    def _handle_cancel_requested(self, event: Event) -> None:
        del event
        self.cancel(wait_ms=0)

    def _handle_listen_requested(self, event: Event) -> None:
        del event
        self._partial_stabilizer.reset()

    def _handle_transcript_ready(
        self,
        thread: _TranscriptionThread,
        transcript: object,
    ) -> None:
        if thread not in self._active_threads or thread in self._cancelled_threads:
            return
        if not isinstance(transcript, VoiceTranscript):
            if self._thread_modes.get(thread) == "final":
                self._voice_controller.report_error(
                    "invalid_transcript",
                    "Speech recognition returned an invalid transcript.",
                )
            return
        if self._thread_modes.get(thread) == "partial":
            stable_text = self._partial_stabilizer.observe(transcript.text)
            if stable_text is None:
                return
            self._event_bus.publish(
                EventType.VOICE_TRANSCRIPT_PARTIAL,
                {
                    "text": stable_text,
                    "detected_language": transcript.detected_language,
                },
            )
            return
        if self._thread_modes.get(thread) == "test":
            confidence_level = voice_confidence_level(transcript.confidence)
            self._voice_controller.complete_input_test()
            payload: dict[str, object] = {
                "detected_language": transcript.detected_language,
                "text_present": bool(transcript.text.strip()),
            }
            if confidence_level is not None:
                payload["confidence_level"] = confidence_level
            self._event_bus.publish(
                EventType.VOICE_MICROPHONE_TEST_COMPLETED,
                payload,
            )
            return
        confidence_level = voice_confidence_level(transcript.confidence)
        self._voice_controller.publish_transcript(
            transcript.text,
            transcript.detected_language,
            confidence_level,
            requires_review=transcript_requires_review(transcript.confidence),
        )

    def _handle_failure(
        self,
        thread: _TranscriptionThread,
        code: str,
        message: str,
    ) -> None:
        if thread not in self._active_threads or thread in self._cancelled_threads:
            return
        if self._thread_modes.get(thread) == "partial":
            return
        self._voice_controller.report_error(code, message)

    def _handle_cancelled(self, thread: _TranscriptionThread) -> None:
        if thread not in self._active_threads:
            return
        if (
            self._thread_modes.get(thread) == "partial"
            and self._pending_final is not None
        ):
            return
        if (
            self._voice_controller.state == VoiceState.THINKING
            and self._voice_controller.operation == "input"
        ):
            self._voice_controller.recover()

    def _remove_thread(self, thread: _TranscriptionThread) -> None:
        if thread in self._active_threads:
            self._active_threads.remove(thread)
        if thread in self._cancelled_threads:
            self._cancelled_threads.remove(thread)
        self._thread_modes.pop(thread, None)
        if self._active_threads:
            return
        if self._pending_final is not None:
            audio = self._pending_final
            self._pending_final = None
            self._start_thread(audio, mode="final")
            return
        if (
            self._pending_partial is not None
            and self._voice_controller.state == VoiceState.LISTENING
            and self._voice_controller.operation == "input"
        ):
            audio = self._pending_partial
            self._pending_partial = None
            self._start_thread(audio, mode="partial")


def _is_related_growth(previous: str, candidate: str) -> bool:
    if len(candidate) <= len(previous):
        return False
    if candidate.startswith(previous):
        return True

    similarity = SequenceMatcher(None, previous, candidate, autojunk=False).ratio()
    prefix_length = 0
    for previous_character, candidate_character in zip(
        previous,
        candidate,
        strict=False,
    ):
        if previous_character != candidate_character:
            break
        prefix_length += 1
    prefix_ratio = prefix_length / max(1, len(previous))
    return similarity >= 0.72 or prefix_ratio >= 0.55
