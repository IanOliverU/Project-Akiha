"""Gemini Live adapter isolated behind provider-neutral session contracts."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from time import monotonic
from typing import Protocol

from project_akiha.core.actions import ActionToolSchema
from project_akiha.core.voice_session import (
    ActionProposal,
    AssistantTextRevision,
    AudioFrame,
    EndpointReason,
    LiveResponseModality,
    LiveSessionCapabilities,
    LiveSessionCapability,
    LiveSessionConfig,
    LiveSessionError,
    LiveSessionErrorCode,
    LiveSessionEventSink,
    LiveSessionStateEvent,
    SanitizedActionResult,
    SessionLifecycle,
    TranscriptRevision,
    TranscriptStatus,
    VoiceCancellationToken,
)

DEFAULT_GEMINI_LIVE_MODEL = "gemini-3.1-flash-live-preview"
_GEMINI_INPUT_RATE_HZ = 16_000
_GEMINI_OUTPUT_RATE_HZ = 24_000
_DEFAULT_MAX_RECONNECT_ATTEMPTS = 2
_DEFAULT_RECONNECT_DELAY_SECONDS = 0.25


class GeminiTransportEventKind(StrEnum):
    """Provider events translated at the Gemini adapter boundary."""

    INPUT_TRANSCRIPT = "input_transcript"
    OUTPUT_TRANSCRIPT = "output_transcript"
    OUTPUT_AUDIO = "output_audio"
    INTERRUPTED = "interrupted"
    TURN_COMPLETE = "turn_complete"
    SESSION_RESUMPTION_UPDATE = "session_resumption_update"
    GO_AWAY = "go_away"
    CLOSED = "closed"
    FAILED = "failed"
    ACTION_PROPOSAL = "action_proposal"


@dataclass(frozen=True, slots=True)
class GeminiLiveTransportConfig:
    """Gemini-specific setup data that never reaches application controllers."""

    model_name: str
    response_modality: LiveResponseModality
    input_audio_transcription: bool
    output_audio_transcription: bool
    context_window_compression: bool
    session_resumption: bool
    voice_name: str = ""
    system_instruction: str = ""
    resumption_handle: str | None = field(default=None, repr=False)
    action_tools: tuple[ActionToolSchema, ...] = ()

    def __post_init__(self) -> None:
        if not self.model_name.strip():
            raise ValueError("Gemini Live model name cannot be empty.")
        if self.resumption_handle is not None:
            if not self.session_resumption:
                raise ValueError("a resumption handle requires session resumption.")
            if not self.resumption_handle.strip():
                raise ValueError("Gemini Live resumption handle cannot be blank.")
            if len(self.resumption_handle) > 4_096:
                raise ValueError("Gemini Live resumption handle is too long.")


@dataclass(frozen=True, slots=True)
class GeminiTransportEvent:
    """Bounded transport event before canonical voice-session translation."""

    kind: GeminiTransportEventKind
    turn_id: str | None = None
    text: str | None = field(default=None, repr=False)
    is_final: bool = False
    detected_language: str | None = None
    audio_data: bytes | None = field(default=None, repr=False)
    error_code: LiveSessionErrorCode | None = None
    error_message: str | None = field(default=None, repr=False)
    retryable: bool = False
    resumption_handle: str | None = field(default=None, repr=False)
    resumable: bool | None = None
    go_away_time_left_seconds: float | None = None
    proposal_id: str | None = None
    action_name: str | None = None
    action_arguments: dict[str, object] | None = field(default=None, repr=False)
    provider_call_id: str | None = field(default=None, repr=False)
    provider_function_name: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.kind in {
            GeminiTransportEventKind.INPUT_TRANSCRIPT,
            GeminiTransportEventKind.OUTPUT_TRANSCRIPT,
        }:
            if not self.text or not self.text.strip():
                raise ValueError("a Gemini transcript event requires text.")
        elif self.text is not None:
            raise ValueError("only Gemini transcript events may contain text.")
        if (
            self.detected_language is not None
            and self.kind is not GeminiTransportEventKind.INPUT_TRANSCRIPT
        ):
            raise ValueError("only input transcripts may include a language.")
        if self.detected_language is not None and not self.detected_language.strip():
            raise ValueError("Gemini transcript language cannot be blank.")
        if self.kind is GeminiTransportEventKind.OUTPUT_AUDIO:
            if not self.audio_data:
                raise ValueError("a Gemini audio event requires PCM data.")
        elif self.audio_data is not None:
            raise ValueError("only Gemini audio events may contain PCM data.")
        if self.kind is GeminiTransportEventKind.FAILED:
            if self.error_code is None or not self.error_message:
                raise ValueError("a Gemini failure event requires a bounded error.")
        elif self.error_code is not None or self.error_message is not None:
            raise ValueError("only Gemini failure events may contain an error.")
        if self.kind is GeminiTransportEventKind.SESSION_RESUMPTION_UPDATE:
            if self.resumable is None:
                raise ValueError("a resumption update requires resumable state.")
            if self.resumable and not self.resumption_handle:
                raise ValueError("a resumable update requires a handle.")
            if (
                self.resumption_handle is not None
                and not self.resumption_handle.strip()
            ):
                raise ValueError("a resumption handle cannot be blank.")
        elif self.resumption_handle is not None or self.resumable is not None:
            raise ValueError("only resumption updates may contain resumption state.")
        if self.kind is GeminiTransportEventKind.GO_AWAY:
            if (
                self.go_away_time_left_seconds is None
                or self.go_away_time_left_seconds < 0
            ):
                raise ValueError("a GoAway event requires non-negative time left.")
        elif self.go_away_time_left_seconds is not None:
            raise ValueError("only GoAway events may contain time left.")
        if self.kind is GeminiTransportEventKind.ACTION_PROPOSAL:
            if not self.proposal_id or not self.action_name:
                raise ValueError(
                    "an action proposal requires correlation and action IDs."
                )
            if self.action_arguments is None:
                raise ValueError("an action proposal requires bounded arguments.")
            if not self.provider_call_id or not self.provider_function_name:
                raise ValueError("an action proposal requires provider correlation.")
        elif any(
            value is not None
            for value in (
                self.proposal_id,
                self.action_name,
                self.action_arguments,
                self.provider_call_id,
                self.provider_function_name,
            )
        ):
            raise ValueError("only action proposals may contain action data.")


class GeminiLiveTransport(Protocol):
    """Injectable transport used by the SDK-neutral Gemini adapter."""

    async def connect(self, config: GeminiLiveTransportConfig) -> None:
        """Open one configured provider session."""

    async def send_audio(self, data: bytes, mime_type: str) -> None:
        """Send one bounded raw PCM audio chunk."""

    async def end_audio_stream(self) -> None:
        """Signal that the current user audio stream ended."""

    async def interrupt(self) -> None:
        """Request interruption of the current model response."""

    async def send_action_result(self, result: SanitizedActionResult) -> None:
        """Return one bounded result for a previously emitted proposal."""

    async def close(self) -> None:
        """Release the provider connection."""

    def receive(self) -> AsyncIterator[GeminiTransportEvent]:
        """Yield provider events until the connection closes."""


class GeminiLiveSessionAdapter:
    """Translate Gemini transport activity into canonical live-session events."""

    def __init__(
        self,
        transport: GeminiLiveTransport,
        *,
        default_model: str = DEFAULT_GEMINI_LIVE_MODEL,
        monotonic_clock: Callable[[], float] = monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        max_reconnect_attempts: int = _DEFAULT_MAX_RECONNECT_ATTEMPTS,
        reconnect_delay_seconds: float = _DEFAULT_RECONNECT_DELAY_SECONDS,
        action_tools: tuple[ActionToolSchema, ...] = (),
    ) -> None:
        if max_reconnect_attempts < 0:
            raise ValueError("Gemini reconnect attempts cannot be negative.")
        if reconnect_delay_seconds < 0:
            raise ValueError("Gemini reconnect delay cannot be negative.")
        self._transport = transport
        self._default_model = default_model
        self._monotonic_clock = monotonic_clock
        self._sleep = sleep
        self._max_reconnect_attempts = max_reconnect_attempts
        self._reconnect_delay_seconds = reconnect_delay_seconds
        self._action_tools = tuple(action_tools)
        self._config: LiveSessionConfig | None = None
        self._event_sink: LiveSessionEventSink | None = None
        self._cancellation_token: VoiceCancellationToken | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._deadline_task: asyncio.Task[None] | None = None
        self._transport_connected = False
        self._lifecycle = SessionLifecycle.IDLE
        self._active_turn_id: str | None = None
        self._input_revision = -1
        self._output_revision = -1
        self._output_audio_sequence = -1
        self._provider_turn_complete = False
        self._interruption_pending_turn_id: str | None = None
        self._logical_deadline_at: float | None = None
        self._resumption_handle: str | None = None
        self._reconnect_attempts = 0

    @property
    def lifecycle(self) -> SessionLifecycle:
        """Return the adapter's current resource-ownership state."""
        return self._lifecycle

    @property
    def capabilities(self) -> LiveSessionCapabilities:
        """Return the Gemini features represented by the V6 contracts."""
        capabilities = {
            LiveSessionCapability.AUDIO_INPUT,
            LiveSessionCapability.AUDIO_OUTPUT,
            LiveSessionCapability.INPUT_TRANSCRIPTION,
            LiveSessionCapability.OUTPUT_TRANSCRIPTION,
            LiveSessionCapability.INTERRUPTION,
            LiveSessionCapability.CONTEXT_COMPRESSION,
            LiveSessionCapability.SESSION_RESUMPTION,
        }
        if self._action_tools:
            capabilities.add(LiveSessionCapability.TOOL_PROPOSALS)
        return LiveSessionCapabilities(
            provider_name="gemini",
            capabilities=frozenset(capabilities),
            input_sample_rate_hz=_GEMINI_INPUT_RATE_HZ,
            output_sample_rate_hz=_GEMINI_OUTPUT_RATE_HZ,
        )

    async def start(
        self,
        config: LiveSessionConfig,
        event_sink: LiveSessionEventSink,
        cancellation_token: VoiceCancellationToken,
    ) -> None:
        """Connect without exposing Gemini SDK objects to the caller."""
        if self._lifecycle is not SessionLifecycle.IDLE:
            raise LiveSessionError(
                LiveSessionErrorCode.INVALID_STATE,
                "The Gemini Live session is already active.",
            )
        if config.provider_name.casefold() != "gemini":
            raise LiveSessionError(
                LiveSessionErrorCode.UNSUPPORTED_CONFIGURATION,
                "The Gemini adapter requires the Gemini live provider.",
            )
        if config.input_sample_rate_hz != _GEMINI_INPUT_RATE_HZ:
            raise LiveSessionError(
                LiveSessionErrorCode.UNSUPPORTED_CONFIGURATION,
                "Gemini Live input must be prepared as 16 kHz PCM.",
            )
        if not config.context_compression_enabled:
            raise LiveSessionError(
                LiveSessionErrorCode.UNSUPPORTED_CONFIGURATION,
                "Gemini Live requires context-window compression.",
            )
        if not config.session_resumption_enabled:
            raise LiveSessionError(
                LiveSessionErrorCode.UNSUPPORTED_CONFIGURATION,
                "Gemini Live requires bounded session resumption.",
            )
        if cancellation_token.is_cancelled:
            raise LiveSessionError(
                LiveSessionErrorCode.CANCELLED,
                "The Gemini Live session was cancelled before startup.",
            )

        self._config = config
        self._event_sink = event_sink
        self._cancellation_token = cancellation_token
        self._logical_deadline_at = (
            self._monotonic_clock() + config.max_duration_seconds
        )
        self._resumption_handle = None
        self._reconnect_attempts = 0
        self._set_lifecycle(SessionLifecycle.STARTING)
        self._transport_connected = True
        try:
            await self._transport.connect(self._transport_config())
        except LiveSessionError as error:
            await self._startup_failed(error)
            raise
        except Exception as error:
            failure = LiveSessionError(
                LiveSessionErrorCode.CONNECTION_FAILED,
                "Gemini Live could not establish a connection.",
                retryable=True,
            )
            await self._startup_failed(failure)
            raise failure from error

        if cancellation_token.is_cancelled:
            await self._close_transport_once()
            self._set_lifecycle(SessionLifecycle.IDLE, "cancelled")
            self._clear_session()
            raise LiveSessionError(
                LiveSessionErrorCode.CANCELLED,
                "The Gemini Live session was cancelled during startup.",
            )

        event_sink.capabilities_received(self.capabilities)
        self._set_lifecycle(SessionLifecycle.ACTIVE)
        self._receive_task = asyncio.create_task(
            self._receive_loop(),
            name=f"gemini-live-receive-{config.session_id}",
        )
        self._deadline_task = asyncio.create_task(
            self._duration_guard(),
            name=f"gemini-live-deadline-{config.session_id}",
        )

    async def accept_audio(self, frame: AudioFrame) -> None:
        """Forward one canonical PCM frame after ownership and format checks."""
        self._require_active()
        config = self._config
        assert config is not None
        if frame.session_id != config.session_id:
            raise LiveSessionError(
                LiveSessionErrorCode.INVALID_STATE,
                "The audio frame belongs to a different live session.",
            )
        if (frame.sample_rate_hz, frame.channels, frame.sample_width_bytes) != (
            config.input_sample_rate_hz,
            1,
            2,
        ):
            raise LiveSessionError(
                LiveSessionErrorCode.UNSUPPORTED_AUDIO_FORMAT,
                "Gemini Live requires mono 16-bit PCM at the configured input rate.",
            )
        if self._active_turn_id is None or self._provider_turn_complete:
            self._begin_turn(frame.turn_id)
        elif frame.turn_id != self._active_turn_id:
            raise LiveSessionError(
                LiveSessionErrorCode.INVALID_STATE,
                "A different live turn still owns the Gemini session.",
            )
        await self._transport.send_audio(
            frame.data,
            f"audio/pcm;rate={frame.sample_rate_hz}",
        )

    async def end_user_turn(self, turn_id: str) -> None:
        """End the active realtime audio stream without ending the session."""
        self._require_owned_turn(turn_id)
        await self._transport.end_audio_stream()

    async def accept_action_result(self, result: SanitizedActionResult) -> None:
        """Return one owned sanitized result through the provider transport."""
        self._require_active()
        if not self._action_tools:
            raise LiveSessionError(
                LiveSessionErrorCode.UNSUPPORTED_CONFIGURATION,
                "Gemini Live tools were not configured for this session.",
            )
        config = self._config
        assert config is not None
        if result.session_id != config.session_id:
            raise LiveSessionError(
                LiveSessionErrorCode.INVALID_STATE,
                "The action result belongs to a different live session.",
            )
        self._require_owned_turn(result.turn_id)
        await self._transport.send_action_result(result)

    async def interrupt(self, turn_id: str) -> None:
        """Request provider-native barge-in and quarantine old-turn output."""
        self._require_owned_turn(turn_id)
        if self._interruption_pending_turn_id == turn_id:
            return
        self._interruption_pending_turn_id = turn_id
        self._provider_turn_complete = True
        await self._transport.interrupt()

    async def stop(self) -> None:
        """Idempotently close receive work and the provider transport."""
        await self._stop_with_reason("stopped")

    async def _stop_with_reason(self, reason: str) -> None:
        if self._lifecycle is SessionLifecycle.IDLE:
            return
        self._set_lifecycle(SessionLifecycle.STOPPING, reason)
        current_task = asyncio.current_task()
        tasks = tuple(
            task
            for task in (self._receive_task, self._deadline_task)
            if task is not None and task is not current_task
        )
        self._receive_task = None
        self._deadline_task = None
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await self._close_transport_once()
        finally:
            self._set_lifecycle(SessionLifecycle.IDLE, reason)
            self._clear_session()

    async def wait_for_receiver(self) -> None:
        """Wait for the current receive task; intended for deterministic tests."""
        task = self._receive_task
        if task is not None:
            await task

    async def _receive_loop(self) -> None:
        while self._lifecycle in {
            SessionLifecycle.ACTIVE,
            SessionLifecycle.STARTING,
        }:
            reconnect_reason: str | None = None
            try:
                async for event in self._transport.receive():
                    if self._lifecycle is not SessionLifecycle.ACTIVE:
                        return
                    token = self._cancellation_token
                    if token is None or token.is_cancelled:
                        return
                    if event.kind is GeminiTransportEventKind.SESSION_RESUMPTION_UPDATE:
                        self._accept_resumption_update(event)
                        continue
                    if event.kind is GeminiTransportEventKind.GO_AWAY:
                        reconnect_reason = "go_away"
                        break
                    self._dispatch(event)
                    if self._lifecycle is not SessionLifecycle.ACTIVE:
                        await self._close_after_failure()
                        return
                else:
                    reconnect_reason = "connection_closed"
            except asyncio.CancelledError:
                raise
            except LiveSessionError as error:
                if error.retryable and error.code in {
                    LiveSessionErrorCode.CONNECTION_CLOSED,
                    LiveSessionErrorCode.CONNECTION_FAILED,
                    LiveSessionErrorCode.PROVIDER_UNAVAILABLE,
                }:
                    reconnect_reason = error.code
                else:
                    self._report_failure(error)
                    await self._close_after_failure()
                    return
            except Exception as error:
                failure = LiveSessionError(
                    LiveSessionErrorCode.PROTOCOL_ERROR,
                    "Gemini Live returned an invalid provider event.",
                    retryable=True,
                )
                self._report_failure(failure)
                del error
                await self._close_after_failure()
                return

            if reconnect_reason is None:
                return
            if not await self._reconnect(reconnect_reason):
                await self._close_after_failure()
                return

    async def _duration_guard(self) -> None:
        try:
            while self._logical_deadline_at is not None:
                remaining = self._logical_deadline_at - self._monotonic_clock()
                if remaining <= 0:
                    break
                await self._sleep(remaining)
            if self._lifecycle in {
                SessionLifecycle.ACTIVE,
                SessionLifecycle.STARTING,
            }:
                await self._stop_with_reason("session_timeout")
        except asyncio.CancelledError:
            raise

    async def _reconnect(self, reason: str) -> bool:
        handle = self._resumption_handle
        if handle is None or self._deadline_reached():
            self._report_failure(
                LiveSessionError(
                    LiveSessionErrorCode.CONNECTION_CLOSED,
                    "Gemini Live could not resume the bounded session.",
                    retryable=True,
                )
            )
            return False

        self._set_lifecycle(SessionLifecycle.STARTING, f"reconnecting:{reason}")
        await self._close_transport_once()
        while self._reconnect_attempts < self._max_reconnect_attempts:
            if self._deadline_reached():
                break
            self._reconnect_attempts += 1
            if self._reconnect_delay_seconds:
                await self._sleep(self._reconnect_delay_seconds)
            self._transport_connected = True
            try:
                await self._transport.connect(self._transport_config(handle))
            except LiveSessionError:
                await self._close_transport_once()
                continue
            except Exception:
                await self._close_transport_once()
                continue
            self._set_lifecycle(SessionLifecycle.ACTIVE, "resumed")
            return True

        self._report_failure(
            LiveSessionError(
                LiveSessionErrorCode.CONNECTION_FAILED,
                "Gemini Live could not reconnect within the bounded retry limit.",
                retryable=True,
            )
        )
        return False

    def _dispatch(self, event: GeminiTransportEvent) -> None:
        sink = self._event_sink
        config = self._config
        if sink is None or config is None:
            return
        if event.kind is GeminiTransportEventKind.INTERRUPTED:
            interrupted_turn_id = self._interruption_pending_turn_id
            if interrupted_turn_id is None:
                return
            sink.response_interrupted(interrupted_turn_id)
            self._interruption_pending_turn_id = None
            return
        turn_id = event.turn_id or self._active_turn_id
        if turn_id is not None and turn_id != self._active_turn_id:
            return
        if self._interruption_pending_turn_id is not None:
            if event.kind in {
                GeminiTransportEventKind.FAILED,
                GeminiTransportEventKind.CLOSED,
            }:
                pass
            elif event.kind is not GeminiTransportEventKind.INPUT_TRANSCRIPT:
                return
            elif turn_id == self._interruption_pending_turn_id:
                return
        if event.kind is GeminiTransportEventKind.INPUT_TRANSCRIPT:
            if turn_id is None:
                return
            self._input_revision += 1
            sink.transcript_revised(
                TranscriptRevision(
                    session_id=config.session_id,
                    turn_id=turn_id,
                    revision_number=self._input_revision,
                    text=event.text or "",
                    status=(
                        TranscriptStatus.FINAL
                        if event.is_final
                        else TranscriptStatus.PARTIAL
                    ),
                    provider_name="gemini-live",
                    detected_language=event.detected_language,
                    endpoint_reason=(
                        EndpointReason.PROVIDER_FINAL if event.is_final else None
                    ),
                )
            )
        elif event.kind is GeminiTransportEventKind.OUTPUT_TRANSCRIPT:
            if turn_id is None:
                return
            self._output_revision += 1
            sink.assistant_text_revised(
                AssistantTextRevision(
                    session_id=config.session_id,
                    turn_id=turn_id,
                    revision_number=self._output_revision,
                    text=event.text or "",
                    is_final=event.is_final,
                )
            )
        elif event.kind is GeminiTransportEventKind.OUTPUT_AUDIO:
            if turn_id is None:
                return
            self._output_audio_sequence += 1
            sink.audio_received(
                AudioFrame(
                    session_id=config.session_id,
                    turn_id=turn_id,
                    sequence_number=self._output_audio_sequence,
                    captured_at_monotonic=monotonic(),
                    sample_rate_hz=_GEMINI_OUTPUT_RATE_HZ,
                    channels=1,
                    sample_width_bytes=2,
                    data=event.audio_data or b"",
                )
            )
        elif event.kind is GeminiTransportEventKind.ACTION_PROPOSAL:
            if turn_id is None:
                raise LiveSessionError(
                    LiveSessionErrorCode.PROTOCOL_ERROR,
                    "Gemini Live proposed an action without an active turn.",
                )
            sink.action_proposed(
                ActionProposal(
                    session_id=config.session_id,
                    turn_id=turn_id,
                    proposal_id=event.proposal_id or "",
                    source="gemini-live",
                    action_name=event.action_name or "",
                    arguments=event.action_arguments or {},
                )
            )
        elif event.kind is GeminiTransportEventKind.TURN_COMPLETE:
            if turn_id is not None:
                sink.turn_completed(turn_id)
                self._provider_turn_complete = True
        elif event.kind is GeminiTransportEventKind.FAILED:
            self._report_failure(
                LiveSessionError(
                    event.error_code or LiveSessionErrorCode.PROTOCOL_ERROR,
                    event.error_message or "Gemini Live failed.",
                    retryable=event.retryable,
                )
            )
        elif event.kind is GeminiTransportEventKind.CLOSED:
            self._report_failure(
                LiveSessionError(
                    LiveSessionErrorCode.CONNECTION_CLOSED,
                    "Gemini Live closed the connection unexpectedly.",
                    retryable=True,
                )
            )

    def _accept_resumption_update(self, event: GeminiTransportEvent) -> None:
        if event.resumable and event.resumption_handle:
            self._resumption_handle = event.resumption_handle
        else:
            self._resumption_handle = None

    def _transport_config(
        self,
        resumption_handle: str | None = None,
    ) -> GeminiLiveTransportConfig:
        config = self._config
        if config is None:
            raise LiveSessionError(
                LiveSessionErrorCode.INVALID_STATE,
                "The Gemini Live session configuration is unavailable.",
            )
        return GeminiLiveTransportConfig(
            model_name=config.model_name.strip() or self._default_model,
            response_modality=config.response_modality,
            voice_name=config.voice_name.strip(),
            system_instruction=config.system_instruction.strip(),
            input_audio_transcription=config.input_transcription_enabled,
            output_audio_transcription=config.output_transcription_enabled,
            context_window_compression=config.context_compression_enabled,
            session_resumption=config.session_resumption_enabled,
            resumption_handle=resumption_handle,
            action_tools=self._action_tools,
        )

    def _deadline_reached(self) -> bool:
        deadline = self._logical_deadline_at
        return deadline is None or self._monotonic_clock() >= deadline

    def _begin_turn(self, turn_id: str) -> None:
        self._active_turn_id = turn_id
        self._input_revision = -1
        self._output_revision = -1
        self._output_audio_sequence = -1
        self._provider_turn_complete = False

    def _require_active(self) -> None:
        if self._lifecycle is not SessionLifecycle.ACTIVE:
            raise LiveSessionError(
                LiveSessionErrorCode.INVALID_STATE,
                "The Gemini Live session is not active.",
            )
        token = self._cancellation_token
        if token is None or token.is_cancelled:
            raise LiveSessionError(
                LiveSessionErrorCode.CANCELLED,
                "The Gemini Live session was cancelled.",
            )

    def _require_owned_turn(self, turn_id: str) -> None:
        self._require_active()
        if not turn_id or turn_id != self._active_turn_id:
            raise LiveSessionError(
                LiveSessionErrorCode.INVALID_STATE,
                "The requested turn does not own the Gemini Live session.",
            )

    async def _startup_failed(self, error: LiveSessionError) -> None:
        self._report_failure(error)
        try:
            await self._close_transport_once()
        finally:
            self._clear_session()

    async def _close_transport_once(self) -> None:
        if not self._transport_connected:
            return
        self._transport_connected = False
        await self._transport.close()

    async def _close_after_failure(self) -> None:
        if self._lifecycle is SessionLifecycle.ERROR:
            await self._close_transport_once()

    def _report_failure(self, error: LiveSessionError) -> None:
        sink = self._event_sink
        if sink is not None:
            sink.failed(error.code, str(error))
        self._set_lifecycle(SessionLifecycle.ERROR, error.code)

    def _set_lifecycle(
        self,
        lifecycle: SessionLifecycle,
        reason: str | LiveSessionErrorCode = "",
    ) -> None:
        self._lifecycle = lifecycle
        sink = self._event_sink
        config = self._config
        if sink is not None and config is not None:
            sink.session_state_changed(
                LiveSessionStateEvent(
                    session_id=config.session_id,
                    provider_name="gemini",
                    lifecycle=lifecycle,
                    reason=str(reason),
                )
            )

    def _clear_session(self) -> None:
        self._config = None
        self._event_sink = None
        self._cancellation_token = None
        self._active_turn_id = None
        self._input_revision = -1
        self._output_revision = -1
        self._output_audio_sequence = -1
        self._provider_turn_complete = False
        self._interruption_pending_turn_id = None
        self._logical_deadline_at = None
        self._resumption_handle = None
        self._reconnect_attempts = 0
        self._deadline_task = None
