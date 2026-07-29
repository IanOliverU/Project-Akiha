"""Tests for the chat response worker."""

from __future__ import annotations

import asyncio
import unittest
from collections.abc import AsyncIterator

from project_akiha.ui.chat_worker import ChatResponseThread


class StreamingController:
    """Test controller that yields configured response chunks."""

    def __init__(self, chunks: tuple[str, ...]) -> None:
        self._chunks = chunks
        self.received_message = ""

    async def stream_user_message(self, message: str) -> AsyncIterator[str]:
        """Yield response chunks for test use."""
        self.received_message = message
        for chunk in self._chunks:
            await asyncio.sleep(0)
            yield chunk


class FailingController:
    """Test controller that raises during provider streaming."""

    async def stream_user_message(self, message: str) -> AsyncIterator[str]:
        """Raise a streaming failure for test use."""
        del message
        raise RuntimeError("provider failed")
        yield ""


class ChatResponseThreadTest(unittest.TestCase):
    """Verify chat worker streaming and cancellation behavior."""

    def test_stream_response_emits_chunks(self) -> None:
        controller = StreamingController(("one", "two"))
        thread = ChatResponseThread(controller, "hello")
        chunks: list[str] = []
        thread.response_delta.connect(chunks.append)

        was_cancelled = asyncio.run(thread._stream_response())

        self.assertFalse(was_cancelled)
        self.assertEqual(chunks, ["one", "two"])
        self.assertEqual(controller.received_message, "hello")

    def test_stream_response_stops_after_cancel(self) -> None:
        controller = StreamingController(("one", "two"))
        thread = ChatResponseThread(controller, "hello")
        chunks: list[str] = []

        def cancel_after_first_chunk(chunk: str) -> None:
            chunks.append(chunk)
            thread.cancel()

        thread.response_delta.connect(cancel_after_first_chunk)

        was_cancelled = asyncio.run(thread._stream_response())

        self.assertTrue(was_cancelled)
        self.assertEqual(chunks, ["one"])

    def test_run_emits_failure_when_provider_stream_fails(self) -> None:
        thread = ChatResponseThread(FailingController(), "hello")
        failures: list[str] = []
        ready_count = 0

        def mark_ready(_result: object) -> None:
            nonlocal ready_count
            ready_count += 1

        thread.response_failed.connect(failures.append)
        thread.response_ready.connect(mark_ready)

        thread.run()

        self.assertEqual(failures, ["provider failed"])
        self.assertEqual(ready_count, 0)


if __name__ == "__main__":
    unittest.main()
