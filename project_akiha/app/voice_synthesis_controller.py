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
        self._event_bus = event_bus
        self._voice_controller = voice_controller
        self._service = service
        self._on_audio_synthesized = on_audio_synthesized
        self._thread_factory = thread_factory
        self._active_threads: list[_SynthesisThread] = []
        self._cancelled_threads: list[_SynthesisThread] = []
        self._last_spoken_text: str | None = None
        self._last_spoken_rate_multiplier = 1.0

        event_bus.subscribe(
            EventType.VOICE_SPEAK_REQUESTED,
            self._handle_speak_requested,
        )
        event_bus.subscribe(
            EventType.VOICE_SPEAK_STOP_REQUESTED,
            self._handle_stop_requested,
        )
        event_bus.subscribe(
            EventType.VOICE_REPLAY_REQUESTED,
            self._handle_replay_requested,
        )

    @property
    def has_replay(self) -> bool:
        """Return whether a previous spoken line can be synthesized again."""
        return self._last_spoken_text is not None

    def apply_service(self, service: SpeechOutputService) -> None:
        """Use an updated provider for the next speech request."""
        self.cancel(wait_ms=0)
        self._service = service

    def clear_replay(self) -> None:
        """Forget the previous spoken text without retaining generated audio."""
        if self._last_spoken_text is None:
            return
        self._last_spoken_text = None
        self._last_spoken_rate_multiplier = 1.0
        self._publish_replay_availability()

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
        spoken_text = text.strip()
        rate_multiplier = _speaking_rate_multiplier(event.payload)
        thread = self._thread_factory(
            self._service,
            spoken_text,
            config.output_voice_id,
            "ja-JP",
            min(2.0, max(0.5, config.speaking_rate * rate_multiplier)),
        )

        def handle_audio_ready(audio: object) -> None:
            self._handle_audio_ready(
                thread,
                audio,
                spoken_text,
                rate_multiplier,
            )

        thread.audio_ready.connect(handle_audio_ready)
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

    def _handle_replay_requested(self, event: Event) -> None:
        del event
        if self._last_spoken_text is None:
            self._voice_controller.notify_error(
                "replay_unavailable",
                "There is no previous spoken response to replay.",
            )
            return
        if self._voice_controller.state != VoiceState.IDLE:
            self._voice_controller.notify_error(
                "replay_busy",
                "Voice must be idle before replaying speech.",
            )
            return
        self._event_bus.publish(
            EventType.VOICE_SPEAK_REQUESTED,
            {
                "text": self._last_spoken_text,
                "source": "replay",
                "speaking_rate_multiplier": self._last_spoken_rate_multiplier,
            },
        )

    def _handle_audio_ready(
        self,
        thread: _SynthesisThread,
        audio: object,
        spoken_text: str,
        rate_multiplier: float,
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
            return
        self._remember_spoken_text(spoken_text, rate_multiplier)

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

    def _remember_spoken_text(self, text: str, rate_multiplier: float) -> None:
        self._last_spoken_text = text
        self._last_spoken_rate_multiplier = rate_multiplier
        self._publish_replay_availability()

    def _publish_replay_availability(self) -> None:
        self._event_bus.publish(
            EventType.VOICE_REPLAY_AVAILABILITY_CHANGED,
            {"available": self.has_replay},
        )


def _speaking_rate_multiplier(payload: dict[str, object]) -> float:
    value = payload.get("speaking_rate_multiplier", 1.0)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0.5 <= value <= 1.5
    ):
        return 1.0
    return float(value)
