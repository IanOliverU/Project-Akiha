"""Tests for explicit hosted-live session lifecycle ownership."""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field

from project_akiha.app.hosted_live_session_controller import (
    HostedLiveSessionController,
)
from project_akiha.app.voice_session_coordinator import VoiceSessionCoordinator
from project_akiha.core.voice_session import (
    ActionProposal,
    AssistantTextRevision,
    AudioFrame,
    LiveResponseModality,
    LiveSessionCapabilities,
    LiveSessionConfig,
    LiveSessionStateEvent,
    SanitizedActionResult,
    SessionLifecycle,
    TranscriptRevision,
    VoiceCancellationToken,
    VoiceProcessingMode,
)


class HostedLiveSessionControllerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.adapter = _Adapter()
        self.coordinator = VoiceSessionCoordinator(
            session_id_factory=lambda: "hosted-session-1"
        )
        self.sink = _Sink()
        self.controller = HostedLiveSessionController(
            adapter=self.adapter,
            coordinator=self.coordinator,
            event_sink=self.sink,
            config_provider=_config,
        )

    async def test_explicit_start_and_end_share_one_coordinator_session(self) -> None:
        self.assertTrue(await self.controller.start())

        config = self.adapter.config
        token = self.adapter.token
        assert config is not None
        assert token is not None
        self.assertEqual(config.session_id, "hosted-session-1")
        self.assertTrue(self.controller.active)
        self.assertEqual(
            self.coordinator.snapshot.lifecycle,
            SessionLifecycle.ACTIVE,
        )
        self.assertFalse(await self.controller.start())

        self.assertTrue(await self.controller.end())

        self.assertTrue(token.is_cancelled)
        self.assertEqual(self.adapter.stop_count, 1)
        self.assertFalse(self.controller.active)
        self.assertEqual(
            self.coordinator.snapshot.lifecycle,
            SessionLifecycle.IDLE,
        )
        self.assertFalse(await self.controller.end())

    async def test_config_must_use_reserved_session_identity(self) -> None:
        controller = HostedLiveSessionController(
            adapter=self.adapter,
            coordinator=self.coordinator,
            event_sink=self.sink,
            config_provider=lambda _session_id: _config("wrong-session"),
        )

        with self.assertRaisesRegex(ValueError, "reserved session ID"):
            await controller.start()

        self.assertEqual(self.coordinator.snapshot.lifecycle, SessionLifecycle.IDLE)
        self.assertEqual(self.adapter.stop_count, 1)
        self.assertFalse(controller.active)

    async def test_provider_timeout_releases_logical_session(self) -> None:
        await self.controller.start()

        self.adapter.emit_stopped("session_timeout")

        self.assertFalse(self.controller.active)
        self.assertEqual(self.coordinator.snapshot.lifecycle, SessionLifecycle.IDLE)
        self.assertEqual(self.sink.states[-1].reason, "session_timeout")

    async def test_reconnect_lifecycle_keeps_logical_session_active(self) -> None:
        await self.controller.start()

        self.adapter.emit_state(SessionLifecycle.STARTING, "reconnecting:go_away")
        self.adapter.emit_state(SessionLifecycle.ACTIVE, "resumed")

        self.assertTrue(self.controller.active)
        self.assertEqual(
            self.coordinator.snapshot.lifecycle,
            SessionLifecycle.ACTIVE,
        )
        self.assertEqual(self.coordinator.snapshot.session_id, "hosted-session-1")

    async def test_provider_failure_enters_error_until_explicit_cleanup(self) -> None:
        await self.controller.start()

        self.adapter.emit_failure("connection_failed", "Hosted live failed.")

        self.assertFalse(self.controller.active)
        self.assertEqual(self.coordinator.snapshot.lifecycle, SessionLifecycle.ERROR)
        self.assertEqual(self.coordinator.snapshot.error_code, "connection_failed")
        self.assertEqual(
            self.sink.failures,
            [("connection_failed", "Hosted live failed.")],
        )

        self.assertTrue(await self.controller.end())
        self.assertEqual(self.coordinator.snapshot.lifecycle, SessionLifecycle.IDLE)


class _Adapter:
    def __init__(self) -> None:
        self.config: LiveSessionConfig | None = None
        self.sink: HostedLiveSessionController | None = None
        self.token: VoiceCancellationToken | None = None
        self.stop_count = 0

    async def start(
        self,
        config: LiveSessionConfig,
        event_sink: HostedLiveSessionController,
        cancellation_token: VoiceCancellationToken,
    ) -> None:
        self.config = config
        self.sink = event_sink
        self.token = cancellation_token
        self.emit_state(SessionLifecycle.STARTING)
        self.emit_state(SessionLifecycle.ACTIVE)

    async def stop(self) -> None:
        self.stop_count += 1
        if self.sink is not None:
            self.emit_stopped("stopped")

    def emit_state(self, lifecycle: SessionLifecycle, reason: str = "") -> None:
        assert self.sink is not None
        assert self.config is not None
        self.sink.session_state_changed(
            LiveSessionStateEvent(
                session_id=self.config.session_id,
                provider_name="gemini",
                lifecycle=lifecycle,
                reason=reason,
            )
        )

    def emit_stopped(self, reason: str) -> None:
        self.emit_state(SessionLifecycle.STOPPING, reason)
        self.emit_state(SessionLifecycle.IDLE, reason)

    def emit_failure(self, code: str, message: str) -> None:
        assert self.sink is not None
        self.sink.failed(code, message)
        self.emit_state(SessionLifecycle.ERROR, code)

    async def accept_audio(self, frame: AudioFrame) -> None:
        del frame

    async def end_user_turn(self, turn_id: str) -> None:
        del turn_id

    async def accept_action_result(self, result: SanitizedActionResult) -> None:
        del result

    async def interrupt(self, turn_id: str) -> None:
        del turn_id


@dataclass
class _Sink:
    states: list[LiveSessionStateEvent] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)

    def transcript_revised(self, revision: TranscriptRevision) -> None:
        del revision

    def assistant_text_revised(self, revision: AssistantTextRevision) -> None:
        del revision

    def audio_received(self, frame: AudioFrame) -> None:
        del frame

    def action_proposed(self, proposal: ActionProposal) -> None:
        del proposal

    def response_interrupted(self, turn_id: str) -> None:
        del turn_id

    def turn_completed(self, turn_id: str) -> None:
        del turn_id

    def failed(self, code: str, message: str) -> None:
        self.failures.append((code, message))

    def session_state_changed(self, event: LiveSessionStateEvent) -> None:
        self.states.append(event)

    def capabilities_received(self, capabilities: LiveSessionCapabilities) -> None:
        del capabilities


def _config(session_id: str = "hosted-session-1") -> LiveSessionConfig:
    return LiveSessionConfig(
        session_id=session_id,
        processing_mode=VoiceProcessingMode.HOSTED_LIVE,
        provider_name="gemini",
        input_sample_rate_hz=16_000,
        max_duration_seconds=600,
        response_modality=LiveResponseModality.AUDIO,
    )


if __name__ == "__main__":
    unittest.main()
