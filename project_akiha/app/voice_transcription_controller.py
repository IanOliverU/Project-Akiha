"""Coordinate local speech recognition workers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from project_akiha.app.voice_controller import VoiceController
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState
from project_akiha.providers.voice import CapturedAudio, VoiceTranscript
from project_akiha.services.speech_input import SpeechInputService
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
        self._voice_controller = voice_controller
        self._service = service
        self._thread_factory = thread_factory
        self._active_threads: list[_TranscriptionThread] = []
        self._cancelled_threads: list[_TranscriptionThread] = []

        event_bus.subscribe(
            EventType.VOICE_LISTEN_CANCEL_REQUESTED,
            self._handle_cancel_requested,
        )

    def apply_service(self, service: SpeechInputService) -> None:
        """Use an updated provider for the next recording."""
        self._service = service

    def submit(self, audio: CapturedAudio) -> None:
        """Start non-blocking transcription for captured PCM."""
        if self._active_threads:
            self._voice_controller.report_error(
                "transcription_busy",
                "Speech recognition is already processing a recording.",
            )
            return

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
        thread.start()

    def cancel(self, wait_ms: int = 2000) -> None:
        """Cancel active transcription and optionally wait during shutdown."""
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

    def _handle_transcript_ready(
        self,
        thread: _TranscriptionThread,
        transcript: object,
    ) -> None:
        if thread not in self._active_threads or thread in self._cancelled_threads:
            return
        if not isinstance(transcript, VoiceTranscript):
            self._voice_controller.report_error(
                "invalid_transcript",
                "Speech recognition returned an invalid transcript.",
            )
            return
        self._voice_controller.publish_transcript(
            transcript.text,
            transcript.detected_language,
        )

    def _handle_failure(
        self,
        thread: _TranscriptionThread,
        code: str,
        message: str,
    ) -> None:
        if thread not in self._active_threads or thread in self._cancelled_threads:
            return
        self._voice_controller.report_error(code, message)

    def _handle_cancelled(self, thread: _TranscriptionThread) -> None:
        if thread not in self._active_threads:
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
