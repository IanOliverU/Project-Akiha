"""Coordinate non-blocking memory work for hosted-live turns."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Protocol

from project_akiha.app.chat_controller import CanonicalLiveChatCommit, ChatController
from project_akiha.ui.live_memory_worker import LiveMemoryProcessingThread


class _MemoryThread(Protocol):
    processing_failed: object
    finished: object

    def start(self) -> None: ...

    def cancel(self) -> None: ...

    def wait(self, time: int = ...) -> bool: ...

    def deleteLater(self) -> None: ...


class LiveMemoryProcessingController:
    """Keep hosted-live memory extraction off Qt's GUI thread."""

    def __init__(
        self,
        chat_controller: ChatController,
        *,
        thread_factory: Callable[
            [ChatController, CanonicalLiveChatCommit],
            _MemoryThread,
        ] = LiveMemoryProcessingThread,
        logger: logging.Logger | None = None,
    ) -> None:
        self._chat_controller = chat_controller
        self._thread_factory = thread_factory
        self._logger = logger or logging.getLogger("project_akiha.memory.live")
        self._active_threads: list[_MemoryThread] = []

    def process(self, commit: CanonicalLiveChatCommit) -> bool:
        """Start deferred memory processing when an assistant reply exists."""
        if commit.assistant_message is None:
            return False
        thread = self._thread_factory(self._chat_controller, commit)
        thread.processing_failed.connect(
            lambda reason, worker=thread: self._handle_failed(worker, reason)
        )
        thread.finished.connect(lambda worker=thread: self._remove_thread(worker))
        self._active_threads.append(thread)
        thread.start()
        return True

    def cancel(self, wait_ms: int = 2_000) -> bool:
        """Cancel pending memory work and report whether every worker stopped."""
        all_stopped = True
        for thread in tuple(self._active_threads):
            thread.cancel()
            if wait_ms > 0 and not thread.wait(wait_ms):
                all_stopped = False
        return all_stopped

    def _handle_failed(self, thread: _MemoryThread, reason: object) -> None:
        if thread not in self._active_threads:
            return
        safe_reason = reason if isinstance(reason, str) else "unknown_error"
        self._logger.warning(
            "Hosted-live memory processing failed (%s).",
            safe_reason,
        )

    def _remove_thread(self, thread: _MemoryThread) -> None:
        if thread in self._active_threads:
            self._active_threads.remove(thread)
        thread.deleteLater()
