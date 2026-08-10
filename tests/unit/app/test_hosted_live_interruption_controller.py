"""Tests for hosted-live local cancellation and provider reconciliation."""

from __future__ import annotations

import unittest

from project_akiha.app.chat_controller import ChatController
from project_akiha.app.hosted_live_interruption_controller import (
    HostedLiveInterruptionController,
)
from project_akiha.app.live_transcript_controller import LiveTranscriptController
from project_akiha.app.voice_session_coordinator import VoiceSessionCoordinator
from project_akiha.core.voice_session import (
    TranscriptRevision,
    TranscriptStatus,
    TurnInterruptionState,
    VoiceInputMode,
    VoiceProcessingMode,
)
from project_akiha.providers.ai import MockAIProvider


class HostedLiveInterruptionControllerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.coordinator = VoiceSessionCoordinator(
            session_id_factory=lambda: "session-1"
        )
        self.coordinator.request_start(VoiceProcessingMode.HOSTED_LIVE)
        self.coordinator.activate()
        self.original_turn = self.coordinator.begin_turn(
            VoiceInputMode.HOSTED_LIVE_CONVERSATION
        )
        self.transcripts = LiveTranscriptController(
            ChatController(MockAIProvider()),
            self.coordinator,
        )
        self.transcripts.start_turn(
            session_id=self.original_turn.session_id,
            turn_id=self.original_turn.turn_id,
        )
        self.adapter = _Adapter()
        self.playback = _Playback()
        self.controller = HostedLiveInterruptionController(
            self.adapter,
            self.coordinator,
            self.transcripts,
            self.playback,
        )

    async def test_interrupt_cancels_local_work_and_transfers_turn_ownership(
        self,
    ) -> None:
        self.transcripts.transcript_revised(_partial(self.original_turn.turn_id))

        result = await self.controller.interrupt_and_replace()

        self.assertTrue(self.playback.cancelled)
        self.assertEqual(self.adapter.interrupted_turns, [self.original_turn.turn_id])
        self.assertEqual(result.interrupted_turn_id, self.original_turn.turn_id)
        self.assertEqual(
            result.replacement_turn,
            self.coordinator.snapshot.active_turn,
        )
        historical = self.coordinator.get_turn(self.original_turn.turn_id)
        assert historical is not None
        self.assertEqual(
            historical.interruption,
            TurnInterruptionState.INTERRUPTED,
        )
        snapshot = self.transcripts.snapshot
        assert snapshot is not None
        self.assertEqual(snapshot.turn_id, result.replacement_turn.turn_id)
        self.assertEqual(
            self.controller.pending_confirmation_turn_id,
            self.original_turn.turn_id,
        )

    async def test_only_matching_provider_confirmation_reconciles(self) -> None:
        await self.controller.interrupt_and_replace()

        self.assertFalse(self.controller.provider_interruption_confirmed("wrong"))
        self.assertTrue(
            self.controller.provider_interruption_confirmed(self.original_turn.turn_id)
        )
        self.assertIsNone(self.controller.pending_confirmation_turn_id)
        self.assertFalse(
            self.controller.provider_interruption_confirmed(self.original_turn.turn_id)
        )

    async def test_late_old_transcript_cannot_mutate_replacement_turn(self) -> None:
        result = await self.controller.interrupt_and_replace()

        accepted = self.transcripts.transcript_revised(
            _partial(self.original_turn.turn_id)
        )

        self.assertFalse(accepted)
        snapshot = self.transcripts.snapshot
        assert snapshot is not None
        self.assertEqual(snapshot.turn_id, result.replacement_turn.turn_id)
        self.assertEqual(snapshot.latest_input_revision, -1)

    async def test_transport_failure_clears_confirmation_wait(self) -> None:
        self.adapter.error = RuntimeError("bounded provider failure")

        with self.assertRaisesRegex(RuntimeError, "bounded provider failure"):
            await self.controller.interrupt_and_replace()

        self.assertIsNone(self.controller.pending_confirmation_turn_id)
        self.assertTrue(self.playback.cancelled)
        self.assertIsNone(self.coordinator.snapshot.active_turn)
        self.assertEqual(
            self.coordinator.snapshot.error_code, "provider_interruption_failed"
        )
        self.assertIsNone(self.transcripts.snapshot)


class _Adapter:
    def __init__(self) -> None:
        self.interrupted_turns: list[str] = []
        self.error: Exception | None = None

    async def interrupt(self, turn_id: str) -> None:
        self.interrupted_turns.append(turn_id)
        if self.error is not None:
            raise self.error


class _Playback:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


def _partial(turn_id: str) -> TranscriptRevision:
    return TranscriptRevision(
        session_id="session-1",
        turn_id=turn_id,
        revision_number=0,
        text="Temporary text",
        status=TranscriptStatus.PARTIAL,
        provider_name="gemini-live",
        endpoint_reason=None,
    )


if __name__ == "__main__":
    unittest.main()
