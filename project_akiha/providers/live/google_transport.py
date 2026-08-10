"""Concrete Google Gen AI SDK transport for Gemini Live sessions."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from project_akiha.core.voice_session import (
    LiveSessionError,
    LiveSessionErrorCode,
)
from project_akiha.providers.live.gemini import (
    GeminiLiveTransportConfig,
    GeminiTransportEvent,
    GeminiTransportEventKind,
)

_PCM_MIME_PATTERN = re.compile(r"^audio/pcm\s*;\s*rate=(\d+)$", re.IGNORECASE)
_MINIMUM_AUDIO_DURATION_SECONDS = 0.020
_MAXIMUM_AUDIO_DURATION_SECONDS = 0.100
_DEFAULT_AUDIO_QUEUE_CAPACITY = 8
_DEFAULT_EVENT_QUEUE_CAPACITY = 64
_DEFAULT_QUEUE_TIMEOUT_SECONDS = 0.250
_CLOSE = object()


@dataclass(frozen=True, slots=True)
class _AudioCommand:
    data: bytes | None = None
    mime_type: str | None = None
    stream_end: bool = False
    activity_start: bool = False


@dataclass(frozen=True, slots=True)
class _TransportFailure:
    error: LiveSessionError


class GoogleGenAILiveTransport:
    """Keep all Google SDK objects behind Akiha's live transport protocol."""

    def __init__(
        self,
        api_key: str,
        *,
        client_factory: Callable[[str], Any] | None = None,
        audio_queue_capacity: int = _DEFAULT_AUDIO_QUEUE_CAPACITY,
        event_queue_capacity: int = _DEFAULT_EVENT_QUEUE_CAPACITY,
        queue_timeout_seconds: float = _DEFAULT_QUEUE_TIMEOUT_SECONDS,
    ) -> None:
        if not api_key.strip():
            raise ValueError("A Gemini Live API key is required.")
        if audio_queue_capacity <= 0 or event_queue_capacity <= 0:
            raise ValueError("Gemini Live queue capacities must be positive.")
        if queue_timeout_seconds <= 0:
            raise ValueError("Gemini Live queue timeout must be positive.")
        self._api_key = api_key.strip()
        self._client_factory = client_factory or _build_google_client
        self._audio_queue_capacity = audio_queue_capacity
        self._event_queue_capacity = event_queue_capacity
        self._queue_timeout_seconds = queue_timeout_seconds
        self._client: Any | None = None
        self._connection_context: Any | None = None
        self._session: Any | None = None
        self._audio_queue: asyncio.Queue[_AudioCommand] | None = None
        self._event_queue: (
            asyncio.Queue[GeminiTransportEvent | _TransportFailure | object] | None
        ) = None
        self._sender_task: asyncio.Task[None] | None = None
        self._receiver_task: asyncio.Task[None] | None = None
        self._closing = False
        self._failed = False
        self._input_transcript_text = ""
        self._output_transcript_text = ""
        self._audio_stream_ended = False
        self._activity_active = False

    @property
    def is_connected(self) -> bool:
        """Return whether one SDK session is currently owned."""
        return self._session is not None and not self._closing and not self._failed

    async def connect(self, config: GeminiLiveTransportConfig) -> None:
        """Open one Google SDK live session and its bounded worker queues."""
        if self._session is not None or self._connection_context is not None:
            raise LiveSessionError(
                LiveSessionErrorCode.INVALID_STATE,
                "The Gemini Live transport is already connected.",
            )
        self._closing = False
        self._failed = False
        self._reset_transcript_text()
        self._audio_stream_ended = False
        self._activity_active = False
        self._audio_queue = asyncio.Queue(maxsize=self._audio_queue_capacity)
        self._event_queue = asyncio.Queue(maxsize=self._event_queue_capacity)
        try:
            self._client = self._client_factory(self._api_key)
            live = self._client.aio.live
            context = live.connect(
                model=config.model_name,
                config=_sdk_connect_config(config),
            )
            self._connection_context = context
            self._session = await context.__aenter__()
        except Exception as error:
            self._connection_context = None
            self._session = None
            self._client = None
            raise _map_sdk_error(error, during_connect=True) from error

        self._sender_task = asyncio.create_task(
            self._send_loop(),
            name="gemini-live-sdk-send",
        )
        self._receiver_task = asyncio.create_task(
            self._receive_loop(),
            name="gemini-live-sdk-receive",
        )

    async def send_audio(self, data: bytes, mime_type: str) -> None:
        """Queue one 20-100 ms PCM16 chunk with bounded backpressure."""
        self._require_connected()
        _validate_pcm_chunk(data, mime_type)
        await self._put_audio(
            _AudioCommand(data=bytes(data), mime_type=mime_type.strip())
        )

    async def end_audio_stream(self) -> None:
        """Queue the stream-end marker after all preceding PCM chunks."""
        self._require_connected()
        await self._put_audio(_AudioCommand(stream_end=True))

    async def interrupt(self) -> None:
        """Start explicit user activity so Gemini interrupts current output."""
        self._require_connected()
        await self._put_audio(_AudioCommand(activity_start=True))

    async def close(self) -> None:
        """Cancel workers, discard queued audio, and close the SDK context."""
        if self._closing:
            return
        self._closing = True
        tasks = tuple(
            task
            for task in (self._sender_task, self._receiver_task)
            if task is not None and task is not asyncio.current_task()
        )
        self._sender_task = None
        self._receiver_task = None
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._discard_audio_queue()
        context = self._connection_context
        self._connection_context = None
        self._session = None
        self._client = None
        try:
            if context is not None:
                await context.__aexit__(None, None, None)
        except Exception:
            pass
        event_queue = self._event_queue
        self._event_queue = None
        if event_queue is not None:
            _put_nowait_replacing_oldest(event_queue, _CLOSE)

    async def receive(self) -> AsyncIterator[GeminiTransportEvent]:
        """Yield translated SDK events without exposing Google model classes."""
        queue = self._event_queue
        if queue is None:
            raise LiveSessionError(
                LiveSessionErrorCode.INVALID_STATE,
                "The Gemini Live transport is not connected.",
            )
        while True:
            item = await queue.get()
            if item is _CLOSE:
                return
            if isinstance(item, _TransportFailure):
                raise item.error
            if isinstance(item, GeminiTransportEvent):
                yield item

    async def _put_audio(self, command: _AudioCommand) -> None:
        queue = self._audio_queue
        if queue is None:
            self._require_connected()
            return
        try:
            await asyncio.wait_for(
                queue.put(command),
                timeout=self._queue_timeout_seconds,
            )
        except TimeoutError as error:
            raise LiveSessionError(
                LiveSessionErrorCode.AUDIO_BACKPRESSURE,
                "Gemini Live audio could not keep pace with the microphone.",
                retryable=True,
            ) from error

    async def _send_loop(self) -> None:
        queue = self._audio_queue
        session = self._session
        if queue is None or session is None:
            return
        try:
            while True:
                command = await queue.get()
                if command.activity_start:
                    await self._start_activity(session)
                    continue
                if command.stream_end:
                    if self._activity_active:
                        await session.send_realtime_input(activity_end={})
                        self._activity_active = False
                    self._audio_stream_ended = True
                    continue
                await self._start_activity(session)
                await session.send_realtime_input(
                    audio={
                        "data": command.data,
                        "mime_type": command.mime_type,
                    }
                )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            await self._report_worker_failure(_map_sdk_error(error))

    async def _start_activity(self, session: Any) -> None:
        if self._activity_active:
            return
        if self._audio_stream_ended:
            self._reset_transcript_text()
            self._audio_stream_ended = False
        await session.send_realtime_input(activity_start={})
        self._activity_active = True

    async def _receive_loop(self) -> None:
        session = self._session
        if session is None:
            return
        try:
            while not self._closing:
                received_any = False
                async for message in session.receive():
                    received_any = True
                    events, input_text, output_text = _translate_sdk_message(
                        message,
                        input_text=self._input_transcript_text,
                        output_text=self._output_transcript_text,
                    )
                    self._input_transcript_text = input_text
                    self._output_transcript_text = output_text
                    for event in events:
                        await self._put_event(event)
                if not received_any and not self._closing:
                    await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            await self._report_worker_failure(_map_sdk_error(error))

    async def _report_worker_failure(self, error: LiveSessionError) -> None:
        if self._closing or self._failed:
            return
        self._failed = True
        await self._put_event(_TransportFailure(error))

    async def _put_event(
        self,
        event: GeminiTransportEvent | _TransportFailure,
    ) -> None:
        queue = self._event_queue
        if queue is None or self._closing:
            return
        try:
            await asyncio.wait_for(
                queue.put(event),
                timeout=self._queue_timeout_seconds,
            )
        except TimeoutError:
            failure = _TransportFailure(
                LiveSessionError(
                    LiveSessionErrorCode.AUDIO_BACKPRESSURE,
                    "Gemini Live output could not keep pace with playback.",
                    retryable=True,
                )
            )
            _put_nowait_replacing_oldest(queue, failure)

    def _require_connected(self) -> None:
        if not self.is_connected:
            raise LiveSessionError(
                LiveSessionErrorCode.INVALID_STATE,
                "The Gemini Live transport is not connected.",
            )

    def _discard_audio_queue(self) -> None:
        queue = self._audio_queue
        self._audio_queue = None
        if queue is None:
            return
        while True:
            try:
                command = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            if command.data is not None:
                del command

    def _reset_transcript_text(self) -> None:
        self._input_transcript_text = ""
        self._output_transcript_text = ""


def _sdk_connect_config(config: GeminiLiveTransportConfig) -> dict[str, object]:
    value: dict[str, object] = {
        "response_modalities": [config.response_modality.value.upper()],
        "realtime_input_config": {
            "automatic_activity_detection": {"disabled": True},
            "activity_handling": "START_OF_ACTIVITY_INTERRUPTS",
        },
    }
    if config.voice_name:
        value["speech_config"] = {
            "voice_config": {"prebuilt_voice_config": {"voice_name": config.voice_name}}
        }
    if config.system_instruction:
        value["system_instruction"] = config.system_instruction
    if config.input_audio_transcription:
        value["input_audio_transcription"] = {}
    if config.output_audio_transcription:
        value["output_audio_transcription"] = {}
    if config.context_window_compression:
        value["context_window_compression"] = {"sliding_window": {}}
    if config.session_resumption:
        value["session_resumption"] = (
            {"handle": config.resumption_handle}
            if config.resumption_handle is not None
            else {}
        )
    return value


def _translate_sdk_message(
    message: object,
    *,
    input_text: str,
    output_text: str,
) -> tuple[tuple[GeminiTransportEvent, ...], str, str]:
    if getattr(message, "tool_call", None) is not None:
        raise LiveSessionError(
            LiveSessionErrorCode.PROTOCOL_ERROR,
            "Gemini Live returned an unexpected tool request before V7.",
        )
    events: list[GeminiTransportEvent] = []
    resumption = getattr(message, "session_resumption_update", None)
    if resumption is not None:
        resumable = bool(getattr(resumption, "resumable", False))
        handle = str(getattr(resumption, "new_handle", "") or "").strip()
        events.append(
            GeminiTransportEvent(
                GeminiTransportEventKind.SESSION_RESUMPTION_UPDATE,
                resumption_handle=handle if resumable and handle else None,
                resumable=resumable and bool(handle),
            )
        )
    go_away = getattr(message, "go_away", None)
    if go_away is not None:
        events.append(
            GeminiTransportEvent(
                GeminiTransportEventKind.GO_AWAY,
                go_away_time_left_seconds=_duration_seconds(
                    getattr(go_away, "time_left", 0)
                ),
            )
        )
        return (
            tuple(events),
            input_text,
            output_text,
        )

    content = getattr(message, "server_content", None)
    if content is None:
        return tuple(events), input_text, output_text
    interim = getattr(content, "interim_input_transcription", None)
    if interim is not None:
        text = str(getattr(interim, "text", "") or "").strip()
        if text:
            events.append(
                GeminiTransportEvent(
                    GeminiTransportEventKind.INPUT_TRANSCRIPT,
                    text=text,
                    is_final=False,
                    detected_language=_optional_language(interim),
                )
            )
    input_transcript = getattr(content, "input_transcription", None)
    if input_transcript is not None:
        input_text = _merge_incremental_text(
            input_text,
            str(getattr(input_transcript, "text", "") or ""),
        )
        if input_text:
            events.append(
                GeminiTransportEvent(
                    GeminiTransportEventKind.INPUT_TRANSCRIPT,
                    text=input_text,
                    is_final=bool(getattr(input_transcript, "finished", False)),
                    detected_language=_optional_language(input_transcript),
                )
            )
    output_transcript = getattr(content, "output_transcription", None)
    if output_transcript is not None:
        output_text = _merge_incremental_text(
            output_text,
            str(getattr(output_transcript, "text", "") or ""),
        )
        if output_text:
            events.append(
                GeminiTransportEvent(
                    GeminiTransportEventKind.OUTPUT_TRANSCRIPT,
                    text=output_text,
                    is_final=bool(getattr(output_transcript, "finished", False)),
                )
            )

    model_turn = getattr(content, "model_turn", None)
    for part in tuple(getattr(model_turn, "parts", None) or ()):
        inline_data = getattr(part, "inline_data", None)
        data = getattr(inline_data, "data", None)
        if isinstance(data, bytes) and data:
            events.append(
                GeminiTransportEvent(
                    GeminiTransportEventKind.OUTPUT_AUDIO,
                    audio_data=data,
                )
            )
    if getattr(content, "interrupted", False):
        events.append(GeminiTransportEvent(GeminiTransportEventKind.INTERRUPTED))
    if getattr(content, "turn_complete", False):
        events.append(GeminiTransportEvent(GeminiTransportEventKind.TURN_COMPLETE))
    return tuple(events), input_text, output_text


def _merge_incremental_text(current: str, incoming: str) -> str:
    current = current.strip()
    incoming = incoming.strip()
    if not incoming:
        return current
    if not current or incoming.startswith(current):
        return incoming
    if current.endswith(incoming):
        return current
    maximum_overlap = min(len(current), len(incoming))
    for overlap in range(maximum_overlap, 0, -1):
        if current[-overlap:] == incoming[:overlap]:
            return current + incoming[overlap:]
    separator = " " if current[-1].isascii() and incoming[0].isascii() else ""
    return current + separator + incoming


def _optional_language(transcription: object) -> str | None:
    value = str(getattr(transcription, "language_code", "") or "").strip()
    return value or None


def _duration_seconds(value: object) -> float:
    total_seconds = getattr(value, "total_seconds", None)
    if callable(total_seconds):
        try:
            seconds = float(total_seconds())
        except (TypeError, ValueError, OverflowError):
            seconds = 0.0
    else:
        try:
            seconds = float(value)
        except (TypeError, ValueError, OverflowError):
            seconds = 0.0
    return min(3_600.0, max(0.0, seconds))


def _validate_pcm_chunk(data: bytes, mime_type: str) -> None:
    if not data or len(data) % 2:
        raise LiveSessionError(
            LiveSessionErrorCode.UNSUPPORTED_AUDIO_FORMAT,
            "Gemini Live audio must contain aligned PCM16 samples.",
        )
    match = _PCM_MIME_PATTERN.fullmatch(mime_type.strip())
    if match is None or int(match.group(1)) != 16_000:
        raise LiveSessionError(
            LiveSessionErrorCode.UNSUPPORTED_AUDIO_FORMAT,
            "Gemini Live audio must be mono PCM16 at 16 kHz.",
        )
    duration = len(data) / 2 / 16_000
    if (
        not _MINIMUM_AUDIO_DURATION_SECONDS
        <= duration
        <= _MAXIMUM_AUDIO_DURATION_SECONDS
    ):
        raise LiveSessionError(
            LiveSessionErrorCode.UNSUPPORTED_AUDIO_FORMAT,
            "Gemini Live audio chunks must represent 20 to 100 milliseconds.",
        )


def _build_google_client(api_key: str) -> object:
    try:
        from google import genai
    except ImportError as error:
        raise LiveSessionError(
            LiveSessionErrorCode.PROVIDER_UNAVAILABLE,
            "Gemini Live requires the optional google-genai package.",
        ) from error
    return genai.Client(api_key=api_key)


def _map_sdk_error(
    error: Exception,
    *,
    during_connect: bool = False,
) -> LiveSessionError:
    if isinstance(error, LiveSessionError):
        return error
    code = getattr(error, "code", None)
    if code in {401, 403}:
        return LiveSessionError(
            LiveSessionErrorCode.AUTHENTICATION_FAILED,
            "Gemini Live rejected the configured API credential.",
        )
    if code == 429:
        return LiveSessionError(
            LiveSessionErrorCode.RATE_LIMITED,
            "Gemini Live quota or rate limits were reached.",
            retryable=True,
        )
    if code in {400, 404, 422}:
        return LiveSessionError(
            LiveSessionErrorCode.UNSUPPORTED_CONFIGURATION,
            "Gemini Live rejected the selected model or session configuration.",
        )
    if code in {500, 502, 503, 504}:
        return LiveSessionError(
            LiveSessionErrorCode.PROVIDER_UNAVAILABLE,
            "Gemini Live is temporarily unavailable.",
            retryable=True,
        )
    return LiveSessionError(
        (
            LiveSessionErrorCode.CONNECTION_FAILED
            if during_connect
            else LiveSessionErrorCode.CONNECTION_CLOSED
        ),
        (
            "Gemini Live could not establish a connection."
            if during_connect
            else "Gemini Live lost its provider connection."
        ),
        retryable=True,
    )


def _put_nowait_replacing_oldest(
    queue: asyncio.Queue[GeminiTransportEvent | _TransportFailure | object],
    item: GeminiTransportEvent | _TransportFailure | object,
) -> None:
    try:
        queue.put_nowait(item)
        return
    except asyncio.QueueFull:
        pass
    try:
        queue.get_nowait()
    except asyncio.QueueEmpty:
        pass
    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        pass
