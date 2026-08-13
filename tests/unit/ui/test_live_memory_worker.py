"""Tests for hosted-live memory processing outside the GUI thread."""

from __future__ import annotations

import unittest

from project_akiha.app.chat_controller import CanonicalLiveChatCommit
from project_akiha.providers.ai import ChatMessage
from project_akiha.ui.live_memory_worker import LiveMemoryProcessingThread


class LiveMemoryProcessingThreadTest(unittest.TestCase):
    def test_processes_persisted_commit(self) -> None:
        controller = _Controller()
        commit = _commit()
        thread = LiveMemoryProcessingThread(controller, commit)

        thread.run()

        self.assertEqual(controller.commits, [commit])

    def test_failure_exposes_only_exception_type(self) -> None:
        controller = _Controller(error=RuntimeError("private conversation text"))
        thread = LiveMemoryProcessingThread(controller, _commit())
        failures: list[str] = []
        thread.processing_failed.connect(failures.append)

        thread.run()

        self.assertEqual(failures, ["RuntimeError"])

    def test_cancelled_worker_skips_processing(self) -> None:
        controller = _Controller()
        thread = LiveMemoryProcessingThread(controller, _commit())
        cancelled: list[bool] = []
        thread.processing_cancelled.connect(lambda: cancelled.append(True))

        thread.cancel()
        thread.run()

        self.assertEqual(controller.commits, [])
        self.assertEqual(cancelled, [True])


class _Controller:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.commits: list[CanonicalLiveChatCommit] = []

    async def process_canonical_live_memory(
        self,
        commit: CanonicalLiveChatCommit,
    ) -> None:
        if self.error is not None:
            raise self.error
        self.commits.append(commit)


def _commit() -> CanonicalLiveChatCommit:
    return CanonicalLiveChatCommit(
        user_message=ChatMessage(role="user", content="Hello"),
        assistant_message=ChatMessage(role="assistant", content="Hello."),
    )


if __name__ == "__main__":
    unittest.main()
