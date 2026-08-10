"""Tests for the concrete Google Gen AI Gemini Live transport."""

from __future__ import annotations

import asyncio
import unittest
from datetime import timedelta
from types import SimpleNamespace

from project_akiha.core.voice_session import (
    LiveResponseModality,
    LiveSessionError,
    LiveSessionErrorCode,
)
from project_akiha.providers.live import (
    GeminiLiveTransportConfig,
    GeminiTransportEventKind,
    GoogleGenAILiveTransport,
)


class GoogleGenAILiveTransportTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.session = _Session()
        self.context = _ConnectContext(self.session)
        self.client = _Client(self.context)
        self.seen_keys: list[str] = []
        self.transport = GoogleGenAILiveTransport(
            "private-api-key",
            client_factory=self._build_client,
        )

    async def asyncTearDown(self) -> None:
        await self.transport.close()

    async def test_connect_maps_config_without_exposing_credentials(self) -> None:
        await self.transport.connect(_config())

        self.assertEqual(self.seen_keys, ["private-api-key"])
        self.assertEqual(self.context.model, "gemini-live-model")
        self.assertEqual(
            self.context.config,
            {
                "response_modalities": ["AUDIO"],
                "realtime_input_config": {
                    "automatic_activity_detection": {"disabled": True},
                    "activity_handling": "START_OF_ACTIVITY_INTERRUPTS",
                },
                "input_audio_transcription": {},
                "output_audio_transcription": {},
                "context_window_compression": {"sliding_window": {}},
                "session_resumption": {},
            },
        )
        self.assertNotIn("private-api-key", repr(self.context.config))

    async def test_audio_and_stream_end_are_sent_in_queue_order(self) -> None:
        await self.transport.connect(_config())

        await self.transport.send_audio(b"\x00\x00" * 320, _PCM_MIME)
        await self.transport.end_audio_stream()
        await _wait_until(lambda: len(self.session.sent) == 3)

        self.assertEqual(
            self.session.sent,
            [
                {"activity_start": {}},
                {
                    "audio": {
                        "data": b"\x00\x00" * 320,
                        "mime_type": _PCM_MIME,
                    }
                },
                {"activity_end": {}},
            ],
        )

    async def test_resumption_handle_is_used_only_for_reconnect_setup(self) -> None:
        config = _config(resumption_handle="private-resumption-handle")

        await self.transport.connect(config)

        self.assertEqual(
            self.context.config["session_resumption"],
            {"handle": "private-resumption-handle"},
        )
        self.assertNotIn("private-resumption-handle", repr(config))

    async def test_interrupt_sends_new_activity_start_after_completed_input(
        self,
    ) -> None:
        await self.transport.connect(_config())
        await self.transport.send_audio(b"\x00\x00" * 320, _PCM_MIME)
        await self.transport.end_audio_stream()
        await self.transport.interrupt()
        await _wait_until(lambda: len(self.session.sent) == 4)

        self.assertEqual(
            self.session.sent,
            [
                {"activity_start": {}},
                {
                    "audio": {
                        "data": b"\x00\x00" * 320,
                        "mime_type": _PCM_MIME,
                    }
                },
                {"activity_end": {}},
                {"activity_start": {}},
            ],
        )

    async def test_sdk_messages_translate_to_bounded_transport_events(self) -> None:
        await self.transport.connect(_config())
        await self.session.emit(
            _message(
                interim_input="Open Spotify",
                input_text="Open Spotify",
                input_finished=True,
                input_language="en-US",
                output_text="Spotify was opened.",
                output_finished=True,
                audio=b"\x01\x02",
                interrupted=True,
                turn_complete=True,
            )
        )

        stream = self.transport.receive()
        events = [await anext(stream) for _ in range(6)]

        self.assertEqual(
            [event.kind for event in events],
            [
                GeminiTransportEventKind.INPUT_TRANSCRIPT,
                GeminiTransportEventKind.INPUT_TRANSCRIPT,
                GeminiTransportEventKind.OUTPUT_TRANSCRIPT,
                GeminiTransportEventKind.OUTPUT_AUDIO,
                GeminiTransportEventKind.INTERRUPTED,
                GeminiTransportEventKind.TURN_COMPLETE,
            ],
        )
        self.assertFalse(events[0].is_final)
        self.assertTrue(events[1].is_final)
        self.assertEqual(events[1].detected_language, "en-US")
        self.assertEqual(events[3].audio_data, b"\x01\x02")

    async def test_incremental_transcript_fragments_become_cumulative_revisions(
        self,
    ) -> None:
        await self.transport.connect(_config())
        await self.session.emit(
            _message(
                input_text="Open",
                output_text="Good",
            )
        )
        await self.session.emit(
            _message(
                input_text="Spotify",
                input_finished=True,
                output_text="morning.",
                output_finished=True,
            )
        )

        stream = self.transport.receive()
        events = [await anext(stream) for _ in range(4)]

        self.assertEqual(
            [event.text for event in events],
            ["Open", "Good", "Open Spotify", "Good morning."],
        )
        self.assertFalse(events[0].is_final)
        self.assertFalse(events[1].is_final)
        self.assertTrue(events[2].is_final)
        self.assertTrue(events[3].is_final)

    async def test_resumption_and_go_away_messages_are_bounded_events(self) -> None:
        await self.transport.connect(_config())
        await self.session.emit(
            _message(
                resumption_handle="private-handle",
                resumable=True,
                go_away_seconds=4.5,
            )
        )

        stream = self.transport.receive()
        events = [await anext(stream) for _ in range(2)]

        self.assertEqual(
            [event.kind for event in events],
            [
                GeminiTransportEventKind.SESSION_RESUMPTION_UPDATE,
                GeminiTransportEventKind.GO_AWAY,
            ],
        )
        self.assertTrue(events[0].resumable)
        self.assertEqual(events[0].resumption_handle, "private-handle")
        self.assertNotIn("private-handle", repr(events[0]))
        self.assertEqual(events[1].go_away_time_left_seconds, 4.5)

    async def test_audio_queue_overflow_is_bounded_and_retryable(self) -> None:
        gate = asyncio.Event()
        self.session.send_gate = gate
        transport = GoogleGenAILiveTransport(
            "private-api-key",
            client_factory=self._build_client,
            audio_queue_capacity=1,
            queue_timeout_seconds=0.01,
        )
        await transport.connect(_config())
        try:
            await transport.send_audio(b"\x00\x00" * 320, _PCM_MIME)
            await self.session.send_started.wait()
            await transport.send_audio(b"\x01\x00" * 320, _PCM_MIME)

            with self.assertRaises(LiveSessionError) as captured:
                await transport.send_audio(b"\x02\x00" * 320, _PCM_MIME)

            self.assertEqual(
                captured.exception.code,
                LiveSessionErrorCode.AUDIO_BACKPRESSURE,
            )
            self.assertTrue(captured.exception.retryable)
        finally:
            gate.set()
            await transport.close()

    async def test_sender_failure_reaches_receive_path_without_raw_detail(self) -> None:
        self.session.send_error = RuntimeError("private websocket failure")
        await self.transport.connect(_config())
        await self.transport.send_audio(b"\x00\x00" * 320, _PCM_MIME)

        with self.assertRaises(LiveSessionError) as captured:
            await anext(self.transport.receive())

        self.assertEqual(
            captured.exception.code,
            LiveSessionErrorCode.CONNECTION_CLOSED,
        )
        self.assertNotIn("private websocket failure", str(captured.exception))
        with self.assertRaises(LiveSessionError) as rejected:
            await self.transport.send_audio(b"\x00\x00" * 320, _PCM_MIME)
        self.assertEqual(rejected.exception.code, LiveSessionErrorCode.INVALID_STATE)

    async def test_invalid_pcm_chunks_are_rejected_before_sdk_dispatch(self) -> None:
        await self.transport.connect(_config())

        invalid = (
            (b"\x00", _PCM_MIME),
            (b"\x00\x00" * 10, _PCM_MIME),
            (b"\x00\x00" * 2_000, _PCM_MIME),
            (b"\x00\x00" * 320, "audio/pcm;rate=48000"),
        )
        for data, mime_type in invalid:
            with self.subTest(size=len(data), mime_type=mime_type):
                with self.assertRaises(LiveSessionError) as captured:
                    await self.transport.send_audio(data, mime_type)
                self.assertEqual(
                    captured.exception.code,
                    LiveSessionErrorCode.UNSUPPORTED_AUDIO_FORMAT,
                )
        self.assertEqual(self.session.sent, [])

    async def test_close_is_idempotent_and_discards_pending_audio(self) -> None:
        await self.transport.connect(_config())
        await self.transport.send_audio(b"\x00\x00" * 320, _PCM_MIME)

        await self.transport.close()
        await self.transport.close()

        self.assertEqual(self.context.exit_count, 1)
        self.assertFalse(self.transport.is_connected)

    async def test_connect_auth_failure_is_sanitized(self) -> None:
        context = _ConnectContext(self.session, enter_error=_SdkError(401))
        transport = GoogleGenAILiveTransport(
            "private-api-key",
            client_factory=lambda _key: _Client(context),
        )

        with self.assertRaises(LiveSessionError) as captured:
            await transport.connect(_config())

        self.assertEqual(
            captured.exception.code,
            LiveSessionErrorCode.AUTHENTICATION_FAILED,
        )
        self.assertNotIn("private-api-key", str(captured.exception))
        await transport.close()

    async def test_unexpected_tool_call_fails_closed_before_v7(self) -> None:
        await self.transport.connect(_config())
        await self.session.emit(SimpleNamespace(tool_call=object(), go_away=None))

        with self.assertRaises(LiveSessionError) as captured:
            await anext(self.transport.receive())

        self.assertEqual(
            captured.exception.code,
            LiveSessionErrorCode.PROTOCOL_ERROR,
        )

    def _build_client(self, api_key: str) -> object:
        self.seen_keys.append(api_key)
        return self.client


class _Session:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []
        self.send_error: Exception | None = None
        self.send_gate: asyncio.Event | None = None
        self.send_started = asyncio.Event()
        self.messages: asyncio.Queue[object] = asyncio.Queue()

    async def send_realtime_input(self, **kwargs: object) -> None:
        self.send_started.set()
        if self.send_gate is not None:
            await self.send_gate.wait()
        if self.send_error is not None:
            raise self.send_error
        self.sent.append(kwargs)

    async def receive(self):
        message = await self.messages.get()
        yield message

    async def emit(self, message: object) -> None:
        await self.messages.put(message)


class _ConnectContext:
    def __init__(
        self,
        session: _Session,
        *,
        enter_error: Exception | None = None,
    ) -> None:
        self.session = session
        self.enter_error = enter_error
        self.model = ""
        self.config: dict[str, object] = {}
        self.exit_count = 0

    async def __aenter__(self) -> _Session:
        if self.enter_error is not None:
            raise self.enter_error
        return self.session

    async def __aexit__(self, *_args: object) -> None:
        self.exit_count += 1


class _Live:
    def __init__(self, context: _ConnectContext) -> None:
        self.context = context

    def connect(self, *, model: str, config: dict[str, object]) -> object:
        self.context.model = model
        self.context.config = config
        return self.context


class _Client:
    def __init__(self, context: _ConnectContext) -> None:
        self.aio = SimpleNamespace(live=_Live(context))


class _SdkError(RuntimeError):
    def __init__(self, code: int) -> None:
        super().__init__("private SDK error")
        self.code = code


def _config(*, resumption_handle: str | None = None) -> GeminiLiveTransportConfig:
    return GeminiLiveTransportConfig(
        model_name="gemini-live-model",
        response_modality=LiveResponseModality.AUDIO,
        input_audio_transcription=True,
        output_audio_transcription=True,
        context_window_compression=True,
        session_resumption=True,
        resumption_handle=resumption_handle,
    )


def _message(
    *,
    interim_input: str = "",
    input_text: str = "",
    input_finished: bool = False,
    input_language: str = "",
    output_text: str = "",
    output_finished: bool = False,
    audio: bytes = b"",
    interrupted: bool = False,
    turn_complete: bool = False,
    resumption_handle: str = "",
    resumable: bool = False,
    go_away_seconds: float | None = None,
) -> object:
    inline_data = SimpleNamespace(data=audio) if audio else None
    model_turn = (
        SimpleNamespace(parts=(SimpleNamespace(inline_data=inline_data),))
        if inline_data is not None
        else None
    )
    content = SimpleNamespace(
        interim_input_transcription=(
            SimpleNamespace(text=interim_input, finished=False)
            if interim_input
            else None
        ),
        input_transcription=(
            SimpleNamespace(
                text=input_text,
                finished=input_finished,
                language_code=input_language,
            )
            if input_text
            else None
        ),
        output_transcription=(
            SimpleNamespace(text=output_text, finished=output_finished)
            if output_text
            else None
        ),
        model_turn=model_turn,
        interrupted=interrupted,
        turn_complete=turn_complete,
    )
    return SimpleNamespace(
        tool_call=None,
        session_resumption_update=(
            SimpleNamespace(
                new_handle=resumption_handle,
                resumable=resumable,
                last_consumed_client_message_index=None,
            )
            if resumption_handle or resumable
            else None
        ),
        go_away=(
            SimpleNamespace(time_left=timedelta(seconds=go_away_seconds))
            if go_away_seconds is not None
            else None
        ),
        server_content=content,
    )


async def _wait_until(predicate, *, attempts: int = 100) -> None:
    for _ in range(attempts):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("Async transport condition was not reached.")


_PCM_MIME = "audio/pcm;rate=16000"


if __name__ == "__main__":
    unittest.main()
