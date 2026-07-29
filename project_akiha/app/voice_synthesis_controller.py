"""Coordinate non-blocking speech synthesis workers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from project_akiha.app.voice_controller import VoiceController
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState
from project_akiha.providers.voice import SynthesizedAudio
from project_akiha.services.speech_output import SpeechOutputService
from project_akiha.ui.voice_synthesis_worker import VoiceSynthesisThread


class _SynthesisThread(Protocol):
    audio_ready: object
    synthesis_failed: object
    synthesis_cancelled: object
    finished: object

    def start(self) -> None:
        """Start synthesis."""

    def cancel(self) -> None:
        """Request cancellation."""

    def wait(self, time: int = ...) -> bool:
        """Wait for completion."""


class VoiceSynthesisController:
    """Run at most one TTS worker and hand audio directly to playback."""

    def __init__(
        self,
        event_bus: EventBus,
        voice_controller: VoiceController,
        service: SpeechOutputService,
        *,
        on_audio_synthesized: Callable[[SynthesizedAudio], None] | None = None,
        thread_factory: Callable[
            [SpeechOutputService, str, str | None, str, float],
            _SynthesisThread,
        ] = VoiceSynthesisThread,
    ) -> None:
        self._voice_controller = voice_controller
        self._service = service
        self._on_audio_synthesized = on_audio_synthesized
        self._thread_factory = thread_factory
        self._active_threads: list[_SynthesisThread] = []
        self._cancelled_threads: list[_SynthesisThread] = []

        event_bus.subscribe(
            EventType.VOICE_SPEAK_REQUESTED,
            self._handle_speak_requested,
        )
        event_bus.subscribe(
            EventType.VOICE_SPEAK_STOP_REQUESTED,
            self._handle_stop_requested,
        )

    def apply_service(self, service: SpeechOutputService) -> None:
        """Use an updated provider for the next speech request."""
        self.cancel(wait_ms=0)
        self._service = service

    def cancel(self, wait_ms: int = 2000) -> None:
        """Cancel active synthesis and optionally wait during shutdown."""
        unfinished = 0
        for thread in tuple(self._active_threads):
            thread.cancel()
            if thread not in self._cancelled_threads:
                self._cancelled_threads.append(thread)
            if wait_ms > 0 and not thread.wait(wait_ms):
                unfinished += 1
        if unfinished:
            raise RuntimeError(f"{unfinished} voice synthesis worker(s) did not stop.")

    def _handle_speak_requested(self, event: Event) -> None:
        if (
            self._voice_controller.state != VoiceState.THINKING
            or self._voice_controller.operation != "output"
        ):
            return
        text = event.payload.get("text")
        if not isinstance(text, str) or not text.strip():
            return
        if self._active_threads:
            self.cancel(wait_ms=0)
            self._voice_controller.report_error(
                "synthesis_busy",
                "Speech synthesis is already processing a request.",
            )
            return

        config = self._voice_controller.config
        thread = self._thread_factory(
            self._service,
            text.strip(),
            config.output_voice_id,
            "ja-JP",
            config.speaking_rate,
        )
        thread.audio_ready.connect(
            lambda audio, worker=thread: self._handle_audio_ready(worker, audio)
        )
        thread.synthesis_failed.connect(
            lambda code, message, worker=thread: self._handle_failure(
                worker,
                code,
                message,
            )
        )
        thread.synthesis_cancelled.connect(
            lambda worker=thread: self._handle_cancelled(worker)
        )
        thread.finished.connect(lambda worker=thread: self._remove_thread(worker))
        self._active_threads.append(thread)
        thread.start()

    def _handle_stop_requested(self, event: Event) -> None:
        del event
        self.cancel(wait_ms=0)

    def _handle_audio_ready(
        self,
        thread: _SynthesisThread,
        audio: object,
    ) -> None:
        if thread not in self._active_threads or thread in self._cancelled_threads:
            return
        if (
            self._voice_controller.state != VoiceState.THINKING
            or self._voice_controller.operation != "output"
        ):
            return
        if not isinstance(audio, SynthesizedAudio):
            self._voice_controller.report_error(
                "invalid_synthesized_audio",
                "Speech synthesis returned invalid audio.",
            )
            return
        if self._on_audio_synthesized is None:
            self._voice_controller.report_error(
                "playback_unavailable",
                "Speech playback is unavailable.",
            )
            return
        try:
            self._on_audio_synthesized(audio)
        except Exception as error:
            self._voice_controller.report_error(
                "playback_failed",
                f"Speech playback failed: {error}",
            )

    def _handle_failure(
        self,
        thread: _SynthesisThread,
        code: str,
        message: str,
    ) -> None:
        if thread not in self._active_threads or thread in self._cancelled_threads:
            return
        self._voice_controller.report_error(code, message)

    def _handle_cancelled(self, thread: _SynthesisThread) -> None:
        if thread not in self._active_threads:
            return
        if (
            self._voice_controller.state == VoiceState.THINKING
            and self._voice_controller.operation == "output"
        ):
            self._voice_controller.recover()

    def _remove_thread(self, thread: _SynthesisThread) -> None:
        if thread in self._active_threads:
            self._active_threads.remove(thread)
        if thread in self._cancelled_threads:
            self._cancelled_threads.remove(thread)
