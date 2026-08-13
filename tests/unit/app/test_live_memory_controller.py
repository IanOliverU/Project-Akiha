"""Tests for non-blocking hosted-live memory coordination."""

from __future__ import annotations

import unittest
from collections.abc import Callable

from project_akiha.app.chat_controller import CanonicalLiveChatCommit
from project_akiha.app.live_memory_controller import LiveMemoryProcessingController
from project_akiha.providers.ai import ChatMessage


class LiveMemoryProcessingControllerTest(unittest.TestCase):
    def test_starts_memory_worker_only_for_complete_exchange(self) -> None:
        threads: list[_Thread] = []
        controller = LiveMemoryProcessingController(
            object(),
            thread_factory=lambda chat, commit: _record_thread(
                threads,
                chat,
                commit,
            ),
        )
        complete = _commit(assistant="Hello.")
        audio_only = _commit(assistant=None)

        self.assertTrue(controller.process(complete))
        self.assertFalse(controller.process(audio_only))
        self.assertTrue(threads[0].started)
        self.assertIs(threads[0].commit, complete)

    def test_cancel_reports_unfinished_worker(self) -> None:
        threads: list[_Thread] = []
        controller = LiveMemoryProcessingController(
            object(),
            thread_factory=lambda chat, commit: _record_thread(
                threads,
                chat,
                commit,
                finished=False,
            ),
        )
        controller.process(_commit(assistant="Hello."))

        self.assertFalse(controller.cancel(wait_ms=25))
        self.assertTrue(threads[0].cancelled)
        self.assertEqual(threads[0].wait_ms, 25)


class _Signal:
    def __init__(self) -> None:
        self.handlers: list[Callable[..., None]] = []

    def connect(self, handler: Callable[..., None]) -> None:
        self.handlers.append(handler)

    def emit(self, *args: object) -> None:
        for handler in tuple(self.handlers):
            handler(*args)


class _Thread:
    def __init__(self, chat: object, commit: CanonicalLiveChatCommit, finished: bool):
        self.processing_failed = _Signal()
        self.finished = _Signal()
        self.chat = chat
        self.commit = commit
        self.finished_result = finished
        self.started = False
        self.cancelled = False
        self.wait_ms = 0
        self.deleted = False

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True

    def wait(self, time: int = 0) -> bool:
        self.wait_ms = time
        return self.finished_result

    def deleteLater(self) -> None:
        self.deleted = True


def _record_thread(
    threads: list[_Thread],
    chat: object,
    commit: CanonicalLiveChatCommit,
    *,
    finished: bool = True,
) -> _Thread:
    thread = _Thread(chat, commit, finished)
    threads.append(thread)
    return thread


def _commit(*, assistant: str | None) -> CanonicalLiveChatCommit:
    return CanonicalLiveChatCommit(
        user_message=ChatMessage(role="user", content="Hello"),
        assistant_message=(
            ChatMessage(role="assistant", content=assistant)
            if assistant is not None
            else None
        ),
    )


if __name__ == "__main__":
    unittest.main()
