"""Tests for coordinated V0 bridge cancellation and shutdown."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.core.actions import (
    ActionPermissionPolicy,
    ActionRequestValidator,
    ProtectedPathPolicy,
    build_default_action_registry,
)
from project_akiha.database import SQLiteActionRepository
from project_akiha.providers.voice import (
    CapturedAudio,
    SpeechSynthesisRequest,
    SynthesizedAudio,
    VoiceProviderHealth,
    VoiceProviderStatus,
    VoiceTranscript,
)
from project_akiha.services.assistant_action_bridge import AssistantActionBridge
from project_akiha.services.assistant_actions import AssistantActionService
from project_akiha.services.assistant_tool_gateway import LLMAssistantToolGateway
from project_akiha.services.speech_input import SpeechInputService
from project_akiha.services.speech_output import SpeechOutputService
from spikes.voice_pipeline.action_gateway_probe import TypedActionGatewayProbe
from spikes.voice_pipeline.bridge_shutdown_probe import VoiceBridgeSessionProbe
from spikes.voice_pipeline.pipeline_spike import ResponseSegment, TranscriptRevision
from spikes.voice_pipeline.qt_audio_bridge import (
    AudioFrame,
    QtSnapshotAudioFrameBridge,
)
from spikes.voice_pipeline.rolling_recognizer import RollingTranscriptRecognizer
from spikes.voice_pipeline.voicevox_processor import OrderedVoiceVoxProcessor


class VoiceBridgeSessionProbeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._temporary_directory = TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        root = Path(self._temporary_directory.name)
        path_policy = ProtectedPathPolicy()
        self.repository = SQLiteActionRepository(root / "akiha.sqlite3")
        action_service = AssistantActionService(
            ActionRequestValidator(build_default_action_registry(), path_policy),
            ActionPermissionPolicy(path_policy),
            self.repository,
            self.repository,
        )
        self.action_provider = _LateActionProvider()
        self.actions = TypedActionGatewayProbe(
            LLMAssistantToolGateway(self.action_provider, enabled=True),
            AssistantActionBridge(action_service),
        )
        self.frames = QtSnapshotAudioFrameBridge()
        self.recognizer = RollingTranscriptRecognizer(
            SpeechInputService(_UnusedInputProvider())
        )
        self.voice_provider = _BlockingVoiceProvider()
        self.output = OrderedVoiceVoxProcessor(SpeechOutputService(self.voice_provider))
        self.playback = _Playback()
        self.session = VoiceBridgeSessionProbe(
            self.frames,
            self.recognizer,
            self.actions,
            self.output,
        )

    async def test_shutdown_releases_all_bridges_and_rejects_late_results(
        self,
    ) -> None:
        self._start_turn(1)
        action_task = asyncio.create_task(
            self.actions.commit_final(
                1,
                TranscriptRevision("Open Spotify", 1, is_final=True),
            )
        )
        self.output.submit(ResponseSegment(1, 0, "Good afternoon."))
        await asyncio.wait_for(self.action_provider.started.wait(), timeout=1.0)
        await asyncio.wait_for(self.voice_provider.started.wait(), timeout=1.0)

        report = await self.session.shutdown()
        self.action_provider.release.set()
        with self.assertRaises(asyncio.CancelledError):
            await action_task

        self.assertEqual(report.turn_id, 1)
        self.assertTrue(report.capture_released)
        self.assertTrue(report.recognition_released)
        self.assertTrue(report.action_invalidated)
        self.assertTrue(report.output_released)
        self.assertEqual(report.errors, ())
        self.assertTrue(self.session.is_closed)
        self.assertEqual(self.playback.texts, [])
        self.assertEqual(await self.repository.get_recent_action_audits(10), ())
        with self.assertRaisesRegex(RuntimeError, "not active"):
            self.frames.accept_snapshot(_captured_audio())
        with self.assertRaisesRegex(RuntimeError, "no active turn"):
            await self.recognizer.accept(_audio_frame(1))
        with self.assertRaisesRegex(RuntimeError, "shut down"):
            self.actions.observe_partial(2, TranscriptRevision("Open", 1))
        with self.assertRaisesRegex(RuntimeError, "shut down"):
            self.session.activate(2)

        repeated = await self.session.shutdown()
        self.assertIsNone(repeated.turn_id)
        self.assertTrue(repeated.capture_released)
        self.assertTrue(repeated.recognition_released)
        self.assertTrue(repeated.output_released)

    async def test_turn_cancellation_allows_a_clean_later_turn(self) -> None:
        self._start_turn(1)

        first = await self.session.cancel_active_turn()

        self.assertFalse(self.session.is_closed)
        self.assertEqual(first.turn_id, 1)
        self.assertIsNone(self.session.active_turn_id)
        self._start_turn(2)
        self.actions.observe_partial(2, TranscriptRevision("Open Discord", 1))

        second = await self.session.cancel_active_turn()

        self.assertEqual(second.turn_id, 2)
        self.assertEqual(second.errors, ())
        self.assertFalse(self.frames.is_active)
        self.assertFalse(self.recognizer.is_active)
        self.assertFalse(self.output.is_active)

    def _start_turn(self, turn_id: int) -> None:
        self.frames.start(session_id="session-1", turn_id=turn_id)
        self.recognizer.start(
            session_id="session-1",
            turn_id=turn_id,
            sample_rate_hz=16_000,
            channels=1,
            sample_width_bytes=2,
        )
        self.output.start_turn(turn_id, self.playback)
        self.session.activate(turn_id)


class _LateActionProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def generate_response(self, messages) -> str:
        del messages
        self.started.set()
        await self.release.wait()
        return '{"action":"launch_application","application_id":"spotify"}'


class _BlockingVoiceProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def health(self) -> VoiceProviderHealth:
        return VoiceProviderHealth(VoiceProviderStatus.AVAILABLE)

    async def synthesize(self, request: SpeechSynthesisRequest) -> SynthesizedAudio:
        self.started.set()
        await self.release.wait()
        return SynthesizedAudio(request.text.encode("utf-8"))

    async def available_voices(self) -> tuple[()]:
        return ()


class _UnusedInputProvider:
    async def health(self) -> VoiceProviderHealth:
        return VoiceProviderHealth(VoiceProviderStatus.AVAILABLE)

    async def transcribe(self, audio: CapturedAudio) -> VoiceTranscript:
        del audio
        return VoiceTranscript("unused")


class _Playback:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def play(
        self,
        segment: ResponseSegment,
        audio: SynthesizedAudio,
    ) -> None:
        del segment
        self.texts.append(audio.data.decode("utf-8"))


def _captured_audio() -> CapturedAudio:
    return CapturedAudio(bytes(3_200), sample_rate_hz=16_000)


def _audio_frame(turn_id: int) -> AudioFrame:
    return AudioFrame(
        session_id="session-1",
        turn_id=turn_id,
        sequence=1,
        captured_at_ns=1,
        data=bytes(3_200),
        sample_rate_hz=16_000,
        channels=1,
        sample_width_bytes=2,
    )


if __name__ == "__main__":
    unittest.main()
