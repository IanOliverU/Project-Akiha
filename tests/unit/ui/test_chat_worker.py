"""Tests for the chat response worker."""

from __future__ import annotations

import asyncio
import unittest
from collections.abc import AsyncIterator

from project_akiha.app.chat_controller import ChatController
from project_akiha.core.voice_session import (
    CanonicalResponseSegment,
    ModularResponseContext,
    ModularResponseEvent,
    ModularResponseEventKind,
    VoiceProcessingMode,
)
from project_akiha.providers.ai import OllamaProvider, OpenAICompatibleProvider
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

        response = asyncio.run(thread._stream_response())

        self.assertEqual(response, "onetwo")
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

        response = asyncio.run(thread._stream_response())

        self.assertIsNone(response)
        self.assertEqual(chunks, ["one"])

    def test_run_emits_completed_response_after_stream_finishes(self) -> None:
        thread = ChatResponseThread(StreamingController(("one", "two")), "hello")
        responses: list[str] = []
        thread.response_ready.connect(responses.append)

        thread.run()

        self.assertEqual(responses, ["onetwo"])

    def test_run_emits_ordered_modular_response_events(self) -> None:
        thread = ChatResponseThread(
            StreamingController(("one", "two")),
            "hello",
            response_context=ModularResponseContext(
                response_id="response-1",
                processing_mode=VoiceProcessingMode.LOCAL_MODULAR,
            ),
        )
        events: list[ModularResponseEvent] = []
        thread.modular_response_event.connect(events.append)

        thread.run()

        self.assertEqual(
            [event.kind for event in events],
            [
                ModularResponseEventKind.STARTED,
                ModularResponseEventKind.DELTA,
                ModularResponseEventKind.DELTA,
                ModularResponseEventKind.COMPLETED,
            ],
        )
        self.assertEqual([event.sequence_number for event in events], [0, 1, 2, 3])
        self.assertEqual(events[-1].text, "onetwo")

    def test_stream_emits_stable_canonical_segments_before_completion(self) -> None:
        thread = ChatResponseThread(
            StreamingController(("First sentence.", " Second sentence begins", ".")),
            "hello",
            response_context=ModularResponseContext(
                response_id="response-segments",
                processing_mode=VoiceProcessingMode.LOCAL_MODULAR,
            ),
        )
        segments: list[CanonicalResponseSegment] = []
        completed: list[str] = []
        thread.response_segment_ready.connect(segments.append)
        thread.response_ready.connect(completed.append)

        thread.run()

        self.assertEqual(
            [segment.canonical_text for segment in segments],
            ["First sentence.", "Second sentence begins."],
        )
        self.assertEqual([segment.is_final for segment in segments], [False, True])
        self.assertEqual(completed, ["First sentence. Second sentence begins."])

    def test_cancel_discards_pending_canonical_segment(self) -> None:
        thread = ChatResponseThread(
            StreamingController(("Incomplete response", " must not flush.")),
            "hello",
        )
        segments: list[CanonicalResponseSegment] = []
        thread.response_segment_ready.connect(segments.append)
        thread.response_delta.connect(lambda _chunk: thread.cancel())

        thread.run()

        self.assertEqual(segments, [])

    def test_run_does_not_emit_response_after_cancellation(self) -> None:
        thread = ChatResponseThread(StreamingController(("one", "two")), "hello")
        responses: list[str] = []
        cancelled: list[bool] = []

        def cancel_after_first_chunk(_chunk: str) -> None:
            thread.cancel()

        thread.response_delta.connect(cancel_after_first_chunk)
        thread.response_ready.connect(responses.append)
        thread.response_cancelled.connect(lambda: cancelled.append(True))

        thread.run()

        self.assertEqual(responses, [])
        self.assertEqual(cancelled, [True])

    def test_cancelled_response_emits_no_completed_event(self) -> None:
        thread = ChatResponseThread(StreamingController(("one", "two")), "hello")
        events: list[ModularResponseEvent] = []
        thread.modular_response_event.connect(events.append)
        thread.response_delta.connect(lambda _chunk: thread.cancel())

        thread.run()

        self.assertEqual(events[-1].kind, ModularResponseEventKind.CANCELLED)
        self.assertNotIn(
            ModularResponseEventKind.COMPLETED,
            [event.kind for event in events],
        )

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

    def test_failure_uses_same_modular_event_path(self) -> None:
        thread = ChatResponseThread(FailingController(), "hello")
        events: list[ModularResponseEvent] = []
        thread.modular_response_event.connect(events.append)

        thread.run()

        self.assertEqual(events[-1].kind, ModularResponseEventKind.FAILED)
        self.assertEqual(events[-1].error_message, "provider failed")
        self.assertIsNone(events[-1].text)

    def test_ollama_and_hosted_provider_emit_identical_event_shapes(self) -> None:
        providers = (
            (
                VoiceProcessingMode.LOCAL_MODULAR,
                OllamaProvider(
                    base_url="http://localhost:11434",
                    model="test",
                    stream_transport=lambda _url, _payload, _timeout: (
                        {"message": {"content": "local response"}},
                        {"done": True},
                    ),
                ),
            ),
            (
                VoiceProcessingMode.HYBRID_API_MODULAR,
                OpenAICompatibleProvider(
                    base_url="https://example.test/v1",
                    model="test",
                    stream_transport=lambda _url, _payload, _headers, _timeout: (
                        {"choices": [{"delta": {"content": "hosted response"}}]},
                    ),
                ),
            ),
        )
        event_shapes = []

        for index, (mode, provider) in enumerate(providers):
            thread = ChatResponseThread(
                ChatController(provider),
                "hello",
                response_context=ModularResponseContext(
                    response_id=f"response-{index}",
                    processing_mode=mode,
                ),
            )
            events: list[ModularResponseEvent] = []
            thread.modular_response_event.connect(events.append)

            thread.run()

            event_shapes.append(
                tuple((event.kind, event.sequence_number) for event in events)
            )
            self.assertTrue(
                all(event.context.processing_mode is mode for event in events)
            )

        self.assertEqual(event_shapes[0], event_shapes[1])


if __name__ == "__main__":
    unittest.main()
