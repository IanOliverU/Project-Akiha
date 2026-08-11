"""Tests for the SDK-neutral Gemini Live adapter foundation."""

from __future__ import annotations

import asyncio
import unittest
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from project_akiha.core.actions import build_default_provider_action_catalog
from project_akiha.core.voice_session import (
    ActionProposal,
    AssistantTextRevision,
    AudioFrame,
    LiveResponseModality,
    LiveSessionCapabilities,
    LiveSessionCapability,
    LiveSessionConfig,
    LiveSessionError,
    LiveSessionErrorCode,
    LiveSessionStateEvent,
    SanitizedActionResult,
    SessionLifecycle,
    TranscriptRevision,
    TranscriptStatus,
    VoiceCancellationToken,
    VoiceProcessingMode,
)
from project_akiha.providers.live import (
    DEFAULT_GEMINI_LIVE_MODEL,
    FakeGeminiLiveTransport,
    GeminiLiveSessionAdapter,
    GeminiLiveTransportConfig,
    GeminiTransportEvent,
    GeminiTransportEventKind,
)


@dataclass
class _Sink:
    states: list[LiveSessionStateEvent] = field(default_factory=list)
    capabilities: list[LiveSessionCapabilities] = field(default_factory=list)
    transcripts: list[TranscriptRevision] = field(default_factory=list)
    assistant_text: list[AssistantTextRevision] = field(default_factory=list)
    audio: list[AudioFrame] = field(default_factory=list)
    proposals: list[ActionProposal] = field(default_factory=list)
    interruptions: list[str] = field(default_factory=list)
    completed_turns: list[str] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)

    def session_state_changed(self, event: LiveSessionStateEvent) -> None:
        self.states.append(event)

    def capabilities_received(self, capabilities: LiveSessionCapabilities) -> None:
        self.capabilities.append(capabilities)

    def transcript_revised(self, revision: TranscriptRevision) -> None:
        self.transcripts.append(revision)

    def assistant_text_revised(self, revision: AssistantTextRevision) -> None:
        self.assistant_text.append(revision)

    def audio_received(self, frame: AudioFrame) -> None:
        self.audio.append(frame)

    def action_proposed(self, proposal: ActionProposal) -> None:
        self.proposals.append(proposal)

    def response_interrupted(self, turn_id: str) -> None:
        self.interruptions.append(turn_id)

    def turn_completed(self, turn_id: str) -> None:
        self.completed_turns.append(turn_id)

    def failed(self, code: str, message: str) -> None:
        self.failures.append((str(code), message))


class _BrokenReceiveTransport(FakeGeminiLiveTransport):
    async def receive(self) -> AsyncIterator[GeminiTransportEvent]:
        raise RuntimeError("private transport exception")
        yield  # pragma: no cover


class GeminiLiveSessionAdapterTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.transport = FakeGeminiLiveTransport()
        self.adapter = GeminiLiveSessionAdapter(
            self.transport,
            reconnect_delay_seconds=0,
        )
        self.sink = _Sink()
        self.token = VoiceCancellationToken()

    async def asyncTearDown(self) -> None:
        await self.adapter.stop()

    async def test_start_reports_capabilities_and_provider_neutral_lifecycle(
        self,
    ) -> None:
        await self._start()

        self.assertEqual(self.adapter.lifecycle, SessionLifecycle.ACTIVE)
        self.assertEqual(
            [event.lifecycle for event in self.sink.states],
            [SessionLifecycle.STARTING, SessionLifecycle.ACTIVE],
        )
        capabilities = self.sink.capabilities[0]
        self.assertTrue(capabilities.supports(LiveSessionCapability.AUDIO_INPUT))
        self.assertTrue(capabilities.supports(LiveSessionCapability.AUDIO_OUTPUT))
        self.assertFalse(capabilities.supports(LiveSessionCapability.TOOL_PROPOSALS))
        self.assertEqual(capabilities.output_sample_rate_hz, 24_000)

    async def test_start_maps_config_without_embedding_credentials(self) -> None:
        await self.adapter.start(
            _config(
                voice_name="Kore",
                system_instruction="Speak as Akiha in Japanese.",
            ),
            self.sink,
            self.token,
        )

        config = self.transport.connected_config
        assert config is not None
        self.assertEqual(config.model_name, DEFAULT_GEMINI_LIVE_MODEL)
        self.assertEqual(config.response_modality, LiveResponseModality.AUDIO)
        self.assertTrue(config.input_audio_transcription)
        self.assertTrue(config.output_audio_transcription)
        self.assertTrue(config.context_window_compression)
        self.assertTrue(config.session_resumption)
        self.assertEqual(config.voice_name, "Kore")
        self.assertEqual(
            config.system_instruction,
            "Speak as Akiha in Japanese.",
        )
        self.assertNotIn("key", repr(config).casefold())

    async def test_start_rejects_non_gemini_provider(self) -> None:
        with self.assertRaisesRegex(LiveSessionError, "requires the Gemini"):
            await self.adapter.start(
                _config(provider_name="other-live"),
                self.sink,
                self.token,
            )

        self.assertEqual(self.adapter.lifecycle, SessionLifecycle.IDLE)
        self.assertIsNone(self.transport.connected_config)

    async def test_start_rejects_audio_that_was_not_prepared_at_16_khz(self) -> None:
        with self.assertRaisesRegex(LiveSessionError, "prepared as 16 kHz"):
            await self.adapter.start(
                _config(input_sample_rate_hz=48_000),
                self.sink,
                self.token,
            )

        self.assertEqual(self.adapter.lifecycle, SessionLifecycle.IDLE)

    async def test_start_requires_compression_and_resumption(self) -> None:
        for config in (
            _config(context_compression_enabled=False),
            _config(session_resumption_enabled=False),
        ):
            with self.subTest(config=config):
                with self.assertRaises(LiveSessionError) as captured:
                    await self.adapter.start(config, self.sink, self.token)
                self.assertEqual(
                    captured.exception.code,
                    LiveSessionErrorCode.UNSUPPORTED_CONFIGURATION,
                )
                self.assertEqual(self.adapter.lifecycle, SessionLifecycle.IDLE)

    async def test_connection_failure_is_sanitized_and_retryable(self) -> None:
        transport = FakeGeminiLiveTransport(
            connect_error=LiveSessionError(
                LiveSessionErrorCode.CONNECTION_FAILED,
                "Gemini Live is temporarily unavailable.",
                retryable=True,
            )
        )
        adapter = GeminiLiveSessionAdapter(transport)
        sink = _Sink()

        with self.assertRaises(LiveSessionError) as raised:
            await adapter.start(_config(), sink, VoiceCancellationToken())

        self.assertTrue(raised.exception.retryable)
        self.assertEqual(sink.failures[0][0], "connection_failed")
        self.assertEqual(adapter.lifecycle, SessionLifecycle.ERROR)
        self.assertEqual(transport.close_count, 1)
        await adapter.stop()
        self.assertEqual(transport.close_count, 1)

    async def test_audio_end_and_interrupt_use_one_owned_turn(self) -> None:
        await self._start()
        await self.adapter.accept_audio(_frame())
        await self.adapter.end_user_turn("turn-1")
        await self.adapter.interrupt("turn-1")
        await self.transport.emit(
            GeminiTransportEvent(GeminiTransportEventKind.INTERRUPTED)
        )
        await self.transport.emit(
            GeminiTransportEvent(GeminiTransportEventKind.INTERRUPTED)
        )
        await _yield_to_receiver()

        self.assertEqual(
            self.transport.sent_audio,
            [(b"\x00\x01", "audio/pcm;rate=16000")],
        )
        self.assertEqual(self.transport.audio_stream_end_count, 1)
        self.assertEqual(self.transport.interrupt_count, 1)
        self.assertEqual(self.sink.interruptions, ["turn-1"])

    async def test_provider_failure_is_not_hidden_by_pending_interruption(self) -> None:
        await self._start()
        await self.adapter.accept_audio(_frame())
        await self.adapter.interrupt("turn-1")
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.FAILED,
                error_code=LiveSessionErrorCode.CONNECTION_CLOSED,
                error_message="Gemini Live lost its provider connection.",
                retryable=True,
            )
        )
        await _yield_to_receiver()

        self.assertEqual(
            self.sink.failures,
            [("connection_closed", "Gemini Live lost its provider connection.")],
        )

    async def test_interruption_drops_old_output_until_provider_confirmation(
        self,
    ) -> None:
        await self._start()
        await self.adapter.accept_audio(_frame())
        await self.adapter.end_user_turn("turn-1")
        await self.adapter.interrupt("turn-1")
        await self.adapter.accept_audio(_frame(turn_id="turn-2"))
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.INPUT_TRANSCRIPT,
                text="Replacement input",
                is_final=False,
            )
        )
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.OUTPUT_TRANSCRIPT,
                text="Stale response",
                is_final=True,
            )
        )
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.OUTPUT_AUDIO,
                audio_data=b"\x01\x02",
            )
        )
        await self.transport.emit(
            GeminiTransportEvent(GeminiTransportEventKind.TURN_COMPLETE)
        )
        await self.transport.emit(
            GeminiTransportEvent(GeminiTransportEventKind.INTERRUPTED)
        )
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.OUTPUT_TRANSCRIPT,
                text="Replacement response",
                is_final=True,
            )
        )
        await _yield_to_receiver()

        self.assertEqual(
            [(revision.turn_id, revision.text) for revision in self.sink.transcripts],
            [("turn-2", "Replacement input")],
        )
        self.assertEqual(
            [revision.text for revision in self.sink.assistant_text],
            ["Replacement response"],
        )
        self.assertEqual(self.sink.audio, [])
        self.assertEqual(self.sink.completed_turns, [])
        self.assertEqual(self.sink.interruptions, ["turn-1"])

    async def test_audio_rejects_wrong_session_format_and_turn(self) -> None:
        await self._start()

        with self.assertRaisesRegex(LiveSessionError, "different live session"):
            await self.adapter.accept_audio(_frame(session_id="other-session"))
        with self.assertRaisesRegex(LiveSessionError, "mono 16-bit PCM"):
            await self.adapter.accept_audio(_frame(sample_rate_hz=48_000))

        await self.adapter.accept_audio(_frame())
        with self.assertRaisesRegex(LiveSessionError, "different live turn"):
            await self.adapter.accept_audio(_frame(turn_id="turn-2"))

    async def test_transport_events_translate_to_canonical_contracts(self) -> None:
        await self._start()
        await self.adapter.accept_audio(_frame())
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.INPUT_TRANSCRIPT,
                turn_id="turn-1",
                text="Hello Akiha",
                is_final=True,
                detected_language="en-US",
            )
        )
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.OUTPUT_TRANSCRIPT,
                turn_id="turn-1",
                text="Good afternoon.",
                is_final=True,
            )
        )
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.OUTPUT_AUDIO,
                turn_id="turn-1",
                audio_data=b"\x02\x03",
            )
        )
        await _yield_to_receiver()

        self.assertEqual(self.sink.transcripts[0].status, TranscriptStatus.FINAL)
        self.assertEqual(self.sink.transcripts[0].text, "Hello Akiha")
        self.assertEqual(self.sink.transcripts[0].detected_language, "en-US")
        self.assertEqual(self.sink.assistant_text[0].text, "Good afternoon.")
        self.assertEqual(self.sink.audio[0].sample_rate_hz, 24_000)
        self.assertEqual(self.sink.audio[0].data, b"\x02\x03")

    async def test_completed_turn_accepts_late_final_text(self) -> None:
        await self._start()
        await self.adapter.accept_audio(_frame())
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.TURN_COMPLETE,
                turn_id="turn-1",
            )
        )
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.OUTPUT_TRANSCRIPT,
                turn_id="turn-1",
                text="Late private output",
                is_final=True,
            )
        )
        await _yield_to_receiver()

        self.assertEqual(self.sink.completed_turns, ["turn-1"])
        self.assertEqual(self.sink.assistant_text[0].text, "Late private output")

    async def test_next_turn_rejects_events_labeled_for_completed_turn(self) -> None:
        await self._start()
        await self.adapter.accept_audio(_frame())
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.TURN_COMPLETE,
                turn_id="turn-1",
            )
        )
        await _yield_to_receiver()
        await self.adapter.accept_audio(_frame(turn_id="turn-2"))
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.OUTPUT_TRANSCRIPT,
                turn_id="turn-1",
                text="Stale private output",
                is_final=True,
            )
        )
        await _yield_to_receiver()

        self.assertEqual(self.sink.assistant_text, [])

    async def test_failure_event_uses_bounded_error_contract(self) -> None:
        await self._start()
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.FAILED,
                error_code=LiveSessionErrorCode.RATE_LIMITED,
                error_message="Gemini Live quota was reached.",
                retryable=True,
            )
        )
        await _yield_to_receiver()

        self.assertEqual(self.adapter.lifecycle, SessionLifecycle.ERROR)
        self.assertEqual(
            self.sink.failures, [("rate_limited", "Gemini Live quota was reached.")]
        )

    async def test_transport_end_without_close_event_is_a_retryable_failure(
        self,
    ) -> None:
        await self._start()

        await self.transport.finish()
        await self.adapter.wait_for_receiver()

        self.assertEqual(self.adapter.lifecycle, SessionLifecycle.ERROR)
        self.assertEqual(self.sink.failures[0][0], "connection_closed")

    async def test_go_away_reconnects_with_latest_memory_only_handle(self) -> None:
        await self._start()
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.SESSION_RESUMPTION_UPDATE,
                resumption_handle="private-resumption-handle",
                resumable=True,
            )
        )
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.GO_AWAY,
                go_away_time_left_seconds=5.0,
            )
        )

        await _wait_until(lambda: self.transport.connect_count == 2)

        self.assertEqual(self.adapter.lifecycle, SessionLifecycle.ACTIVE)
        resumed = self.transport.connected_configs[-1]
        self.assertEqual(resumed.resumption_handle, "private-resumption-handle")
        self.assertNotIn("private-resumption-handle", repr(resumed))
        self.assertEqual(
            [(event.lifecycle, event.reason) for event in self.sink.states[-2:]],
            [
                (SessionLifecycle.STARTING, "reconnecting:go_away"),
                (SessionLifecycle.ACTIVE, "resumed"),
            ],
        )

    async def test_go_away_without_resumption_handle_fails_visibly(self) -> None:
        await self._start()

        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.GO_AWAY,
                go_away_time_left_seconds=5.0,
            )
        )
        await _wait_until(lambda: self.adapter.lifecycle is SessionLifecycle.ERROR)

        self.assertEqual(self.transport.connect_count, 1)
        self.assertEqual(self.transport.close_count, 1)
        self.assertEqual(self.sink.failures[-1][0], "connection_closed")

    async def test_non_resumable_update_revokes_previous_handle(self) -> None:
        await self._start()
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.SESSION_RESUMPTION_UPDATE,
                resumption_handle="private-resumption-handle",
                resumable=True,
            )
        )
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.SESSION_RESUMPTION_UPDATE,
                resumable=False,
            )
        )
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.GO_AWAY,
                go_away_time_left_seconds=5.0,
            )
        )

        await _wait_until(lambda: self.adapter.lifecycle is SessionLifecycle.ERROR)

        self.assertEqual(self.transport.connect_count, 1)
        self.assertEqual(self.sink.failures[-1][0], "connection_closed")

    async def test_unexpected_connection_close_resumes_when_handle_exists(
        self,
    ) -> None:
        await self._start()
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.SESSION_RESUMPTION_UPDATE,
                resumption_handle="private-resumption-handle",
                resumable=True,
            )
        )
        await self.transport.finish()

        await _wait_until(lambda: self.transport.connect_count == 2)

        self.assertEqual(self.adapter.lifecycle, SessionLifecycle.ACTIVE)
        self.assertEqual(
            self.transport.connected_configs[-1].resumption_handle,
            "private-resumption-handle",
        )

    async def test_reconnect_attempts_are_bounded(self) -> None:
        await self._start()
        self.transport.connect_errors.extend(
            [
                LiveSessionError(
                    LiveSessionErrorCode.CONNECTION_FAILED,
                    "Reconnect failed.",
                    retryable=True,
                ),
                LiveSessionError(
                    LiveSessionErrorCode.CONNECTION_FAILED,
                    "Reconnect failed again.",
                    retryable=True,
                ),
            ]
        )
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.SESSION_RESUMPTION_UPDATE,
                resumption_handle="private-resumption-handle",
                resumable=True,
            )
        )
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.GO_AWAY,
                go_away_time_left_seconds=5.0,
            )
        )

        await _wait_until(lambda: self.adapter.lifecycle is SessionLifecycle.ERROR)

        self.assertEqual(self.transport.connect_count, 3)
        self.assertEqual(self.sink.failures[-1][0], "connection_failed")

    async def test_audio_is_rejected_while_connection_is_resuming(self) -> None:
        transport = _GatedReconnectTransport()
        adapter = GeminiLiveSessionAdapter(transport, reconnect_delay_seconds=0)
        await adapter.start(_config(), self.sink, self.token)
        await transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.SESSION_RESUMPTION_UPDATE,
                resumption_handle="private-resumption-handle",
                resumable=True,
            )
        )
        await transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.GO_AWAY,
                go_away_time_left_seconds=5.0,
            )
        )
        await transport.reconnect_started.wait()

        with self.assertRaises(LiveSessionError) as captured:
            await adapter.accept_audio(_frame())
        self.assertEqual(captured.exception.code, LiveSessionErrorCode.INVALID_STATE)

        transport.allow_reconnect.set()
        await _wait_until(lambda: adapter.lifecycle is SessionLifecycle.ACTIVE)
        await adapter.stop()

    async def test_reconnect_does_not_extend_logical_session_deadline(self) -> None:
        clock = _FakeClock()
        sleeper = _ControlledSleep()
        transport = FakeGeminiLiveTransport()
        adapter = GeminiLiveSessionAdapter(
            transport,
            monotonic_clock=clock,
            sleep=sleeper,
            reconnect_delay_seconds=0,
        )
        await adapter.start(
            _config(max_duration_seconds=5),
            self.sink,
            self.token,
        )
        await sleeper.started.wait()
        clock.advance(4)
        await transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.SESSION_RESUMPTION_UPDATE,
                resumption_handle="private-resumption-handle",
                resumable=True,
            )
        )
        await transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.GO_AWAY,
                go_away_time_left_seconds=5.0,
            )
        )
        await _wait_until(lambda: transport.connect_count == 2)

        clock.advance(1)
        sleeper.release.set()
        await _wait_until(lambda: adapter.lifecycle is SessionLifecycle.IDLE)

        self.assertEqual(sleeper.delays, [5.0])
        self.assertEqual(self.sink.states[-1].reason, "session_timeout")
        self.assertEqual(transport.connect_count, 2)

    async def test_unexpected_receive_error_is_reported_without_task_failure(
        self,
    ) -> None:
        adapter = GeminiLiveSessionAdapter(_BrokenReceiveTransport())
        sink = _Sink()
        await adapter.start(_config(), sink, VoiceCancellationToken())

        await adapter.wait_for_receiver()

        self.assertEqual(adapter.lifecycle, SessionLifecycle.ERROR)
        self.assertEqual(
            sink.failures,
            [("protocol_error", "Gemini Live returned an invalid provider event.")],
        )
        self.assertNotIn("private transport exception", repr(sink.failures))
        await adapter.stop()

    async def test_cancelled_session_rejects_new_audio(self) -> None:
        await self._start()
        self.token.cancel()

        with self.assertRaises(LiveSessionError) as raised:
            await self.adapter.accept_audio(_frame())

        self.assertEqual(raised.exception.code, LiveSessionErrorCode.CANCELLED)
        self.assertEqual(self.transport.sent_audio, [])

    async def test_tool_result_requires_an_explicit_tool_catalog(self) -> None:
        await self._start()

        with self.assertRaisesRegex(LiveSessionError, "not configured"):
            await self.adapter.accept_action_result(
                SanitizedActionResult(
                    session_id="session-1",
                    turn_id="turn-1",
                    proposal_id="proposal-1",
                    status="success",
                    message="Done.",
                )
            )

    async def test_tool_proposal_and_result_use_provider_neutral_contracts(
        self,
    ) -> None:
        tools = build_default_provider_action_catalog().schemas
        adapter = GeminiLiveSessionAdapter(
            self.transport,
            reconnect_delay_seconds=0,
            action_tools=tools,
        )
        await adapter.start(_config(), self.sink, self.token)
        await adapter.accept_audio(_frame())
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.ACTION_PROPOSAL,
                proposal_id="gemini-tool-1",
                action_name="spotify.pause",
                action_arguments={"service": "spotify"},
                provider_call_id="private-sdk-call-id",
                provider_function_name="akiha_spotify_pause",
            )
        )
        await _wait_until(lambda: bool(self.sink.proposals))

        self.assertTrue(
            adapter.capabilities.supports(LiveSessionCapability.TOOL_PROPOSALS)
        )
        proposal = self.sink.proposals[0]
        self.assertEqual(proposal.action_name, "spotify.pause")
        self.assertEqual(proposal.source, "gemini-live")
        result = SanitizedActionResult(
            session_id="session-1",
            turn_id="turn-1",
            proposal_id="gemini-tool-1",
            status="success",
            message="The approved action completed.",
        )
        await adapter.accept_action_result(result)

        self.assertEqual(self.transport.action_results, [result])
        await adapter.stop()

    async def test_tool_proposal_without_an_owned_turn_fails_closed(self) -> None:
        adapter = GeminiLiveSessionAdapter(
            self.transport,
            reconnect_delay_seconds=0,
            action_tools=build_default_provider_action_catalog().schemas,
        )
        await adapter.start(_config(), self.sink, self.token)
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.ACTION_PROPOSAL,
                proposal_id="gemini-tool-unowned",
                action_name="spotify.pause",
                action_arguments={"service": "spotify"},
                provider_call_id="private-sdk-call-id",
                provider_function_name="akiha_spotify_pause",
            )
        )
        await _wait_until(lambda: adapter.lifecycle is SessionLifecycle.ERROR)

        self.assertEqual(self.sink.proposals, [])
        self.assertEqual(self.sink.failures[0][0], "protocol_error")
        await adapter.stop()

    async def test_stop_is_idempotent_and_suppresses_late_events(self) -> None:
        await self._start()
        await self.adapter.accept_audio(_frame())

        await self.adapter.stop()
        await self.adapter.stop()
        await self.transport.emit(
            GeminiTransportEvent(
                GeminiTransportEventKind.OUTPUT_TRANSCRIPT,
                turn_id="turn-1",
                text="Late output after stop",
            )
        )
        await _yield_to_receiver()

        self.assertEqual(self.adapter.lifecycle, SessionLifecycle.IDLE)
        self.assertEqual(self.transport.close_count, 1)
        self.assertEqual(self.sink.assistant_text, [])

    async def _start(self) -> None:
        await self.adapter.start(_config(), self.sink, self.token)


def _config(
    *,
    provider_name: str = "gemini",
    input_sample_rate_hz: int = 16_000,
    max_duration_seconds: int = 600,
    context_compression_enabled: bool = True,
    session_resumption_enabled: bool = True,
    voice_name: str = "",
    system_instruction: str = "",
) -> LiveSessionConfig:
    return LiveSessionConfig(
        session_id="session-1",
        processing_mode=VoiceProcessingMode.HOSTED_LIVE,
        provider_name=provider_name,
        input_sample_rate_hz=input_sample_rate_hz,
        max_duration_seconds=max_duration_seconds,
        voice_name=voice_name,
        system_instruction=system_instruction,
        context_compression_enabled=context_compression_enabled,
        session_resumption_enabled=session_resumption_enabled,
    )


def _frame(
    *,
    session_id: str = "session-1",
    turn_id: str = "turn-1",
    sample_rate_hz: int = 16_000,
) -> AudioFrame:
    return AudioFrame(
        session_id=session_id,
        turn_id=turn_id,
        sequence_number=0,
        captured_at_monotonic=1.0,
        sample_rate_hz=sample_rate_hz,
        channels=1,
        sample_width_bytes=2,
        data=b"\x00\x01",
    )


async def _yield_to_receiver() -> None:
    await asyncio.sleep(0)
    await asyncio.sleep(0)


async def _wait_until(predicate, *, attempts: int = 100) -> None:
    for _ in range(attempts):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("Async Gemini adapter condition was not reached.")


class _GatedReconnectTransport(FakeGeminiLiveTransport):
    def __init__(self) -> None:
        super().__init__()
        self.reconnect_started = asyncio.Event()
        self.allow_reconnect = asyncio.Event()

    async def connect(self, config: GeminiLiveTransportConfig) -> None:
        if self.connect_count:
            self.reconnect_started.set()
            await self.allow_reconnect.wait()
        await super().connect(config)


class _FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _ControlledSleep:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)
        self.started.set()
        await self.release.wait()


if __name__ == "__main__":
    unittest.main()
