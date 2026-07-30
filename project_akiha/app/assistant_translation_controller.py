"""Coordinate optional, non-canonical English assistant subtitles."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Protocol

from project_akiha.config import VoiceConfig
from project_akiha.services.assistant_translation import AssistantTranslationService
from project_akiha.ui.assistant_translation_worker import AssistantTranslationThread


class AssistantTranslationSurface(Protocol):
    """Chat presentation used by the subtitle controller."""

    def append_assistant_translation(self, content: str) -> None:
        """Display translated text separately from the canonical response."""

    def append_translation_unavailable(self) -> None:
        """Display a quiet, non-fatal subtitle fallback."""


class _TranslationThread(Protocol):
    translation_ready: object
    translation_failed: object
    translation_cancelled: object
    finished: object

    def start(self) -> None:
        """Start translation."""

    def cancel(self) -> None:
        """Request cancellation."""

    def wait(self, time: int = ...) -> bool:
        """Wait for completion."""

    def deleteLater(self) -> None:
        """Schedule Qt cleanup."""


class AssistantTranslationController:
    """Run optional subtitle translation without touching chat persistence."""

    def __init__(
        self,
        service: AssistantTranslationService,
        surface: AssistantTranslationSurface,
        config: VoiceConfig,
        *,
        thread_factory: Callable[
            [AssistantTranslationService, str, int | None],
            _TranslationThread,
        ] = AssistantTranslationThread,
        message_id_provider: Callable[[], int | None] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._service = service
        self._surface = surface
        self._config = config
        self._thread_factory = thread_factory
        self._message_id_provider = message_id_provider
        self._logger = logger or logging.getLogger("project_akiha.voice.translation")
        self._active_threads: list[_TranslationThread] = []
        self._cancelled_threads: list[_TranslationThread] = []

    def apply_config(self, config: VoiceConfig) -> None:
        """Apply subtitle settings and cancel work when subtitles are disabled."""
        self._config = config
        if not config.english_subtitles_enabled:
            self.cancel(wait_ms=0)

    def apply_service(self, service: AssistantTranslationService) -> None:
        """Use a new provider-backed service for subsequent translations."""
        self.cancel(wait_ms=0)
        self._service = service

    def translate_assistant_response(self, text: str) -> bool:
        """Start translation for one completed response when enabled."""
        if (
            not self._config.english_subtitles_enabled
            or not isinstance(text, str)
            or not text.strip()
        ):
            return False

        message_id = (
            self._message_id_provider()
            if self._message_id_provider is not None
            else None
        )
        thread = self._thread_factory(self._service, text.strip(), message_id)
        thread.translation_ready.connect(
            lambda translation, worker=thread: self._handle_ready(
                worker,
                translation,
            )
        )
        thread.translation_failed.connect(
            lambda reason, worker=thread: self._handle_failed(worker, reason)
        )
        thread.finished.connect(lambda worker=thread: self._remove_thread(worker))
        self._active_threads.append(thread)
        thread.start()
        return True

    def cancel(self, wait_ms: int = 2000) -> bool:
        """Cancel translations and return whether every worker stopped."""
        all_stopped = True
        for thread in tuple(self._active_threads):
            thread.cancel()
            if thread not in self._cancelled_threads:
                self._cancelled_threads.append(thread)
            if wait_ms > 0 and not thread.wait(wait_ms):
                all_stopped = False
        return all_stopped

    def _handle_ready(
        self,
        thread: _TranslationThread,
        translation: object,
    ) -> None:
        if thread not in self._active_threads or thread in self._cancelled_threads:
            return
        if not isinstance(translation, str) or not translation.strip():
            self._handle_failed(thread, "invalid_result")
            return
        self._surface.append_assistant_translation(translation.strip())

    def _handle_failed(self, thread: _TranslationThread, reason: object) -> None:
        if thread not in self._active_threads or thread in self._cancelled_threads:
            return
        safe_reason = reason if isinstance(reason, str) else "unknown_error"
        self._logger.warning("English subtitle translation failed (%s).", safe_reason)
        self._surface.append_translation_unavailable()

    def _remove_thread(self, thread: _TranslationThread) -> None:
        if thread in self._active_threads:
            self._active_threads.remove(thread)
        if thread in self._cancelled_threads:
            self._cancelled_threads.remove(thread)
        thread.deleteLater()
