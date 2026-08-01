"""Tests for voice turn ownership and stale-result rejection."""

from __future__ import annotations

import unittest

from project_akiha.core.voice_session import (
    EndpointReason,
    RecognitionStage,
    TranscriptRevision,
    TranscriptStatus,
    TurnInterruptionState,
    VoiceInputMode,
    VoiceProcessingMode,
    VoiceTurnLedger,
)


class VoiceTurnLedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = VoiceTurnLedger("session-1")

    def test_begin_turn_assigns_monotonic_session_scoped_ids(self) -> None:
        first = self._begin()
        self.ledger.complete_active()
        second = self._begin()

        self.assertEqual(first.turn_id, "1")
        self.assertEqual(second.turn_id, "2")
        self.assertEqual(second.session_id, "session-1")

    def test_begin_turn_refuses_implicit_replacement(self) -> None:
        self._begin()

        with self.assertRaisesRegex(RuntimeError, "already exists"):
            self._begin()

    def test_newer_partial_replaces_preview_without_becoming_canonical(self) -> None:
        turn = self._begin()

        self.assertTrue(self.ledger.accept_transcript_revision(self._partial(turn, 0)))
        self.assertTrue(self.ledger.accept_transcript_revision(self._partial(turn, 1)))

        current = self.ledger.active_turn
        assert current is not None
        self.assertEqual(current.latest_transcript_revision, 1)
        self.assertIsNone(current.accepted_final_transcript)
        self.assertEqual(current.stages.recognition, RecognitionStage.PARTIAL)

    def test_out_of_order_revision_is_rejected(self) -> None:
        turn = self._begin()
        self.assertTrue(self.ledger.accept_transcript_revision(self._partial(turn, 2)))

        self.assertFalse(self.ledger.accept_transcript_revision(self._partial(turn, 1)))
        self.assertEqual(self.ledger.active_turn.latest_transcript_revision, 2)  # type: ignore[union-attr]

    def test_final_revision_becomes_canonical_and_closes_revision_stream(self) -> None:
        turn = self._begin()
        final = self._final(turn, 3, "Open Discord")

        self.assertTrue(self.ledger.accept_transcript_revision(final))
        self.assertFalse(self.ledger.accept_transcript_revision(self._partial(turn, 4)))

        current = self.ledger.active_turn
        assert current is not None
        self.assertEqual(current.accepted_final_transcript, final)
        self.assertEqual(current.stages.recognition, RecognitionStage.FINAL)

    def test_replacement_cancels_old_token_and_rejects_late_result(self) -> None:
        old_turn = self._begin()
        replacement = self.ledger.replace_turn(
            input_mode=VoiceInputMode.PUSH_TO_TALK,
            processing_mode=VoiceProcessingMode.LOCAL_MODULAR,
        )

        self.assertTrue(old_turn.cancellation_token.is_cancelled)
        self.assertEqual(
            self.ledger.get_turn(old_turn.turn_id).interruption,  # type: ignore[union-attr]
            TurnInterruptionState.INTERRUPTED,
        )
        self.assertFalse(
            self.ledger.accept_transcript_revision(
                self._final(old_turn, 0, "Stale private transcript")
            )
        )
        self.assertEqual(self.ledger.active_turn, replacement)
        self.assertIsNone(replacement.accepted_final_transcript)

    def test_wrong_session_callback_is_rejected(self) -> None:
        turn = self._begin()
        revision = TranscriptRevision(
            session_id="other-session",
            turn_id=turn.turn_id,
            revision_number=0,
            text="Wrong owner",
            status=TranscriptStatus.PARTIAL,
            provider_name="fake",
        )

        self.assertFalse(self.ledger.accept_transcript_revision(revision))

    def test_completed_turn_no_longer_accepts_callbacks(self) -> None:
        turn = self._begin()
        self.ledger.complete_active()

        self.assertFalse(self.ledger.accept_transcript_revision(self._partial(turn, 0)))

    def test_cancel_is_idempotent(self) -> None:
        turn = self._begin()

        first = self.ledger.cancel_active()
        second = self.ledger.cancel_active()

        self.assertTrue(turn.cancellation_token.is_cancelled)
        self.assertEqual(first.interruption, TurnInterruptionState.CANCELLED)  # type: ignore[union-attr]
        self.assertIsNone(second)

    def test_close_cancels_active_turn_and_rejects_future_work(self) -> None:
        turn = self._begin()

        self.ledger.close()

        self.assertTrue(turn.cancellation_token.is_cancelled)
        self.assertFalse(self.ledger.accepts_callback("session-1", turn.turn_id))
        with self.assertRaisesRegex(RuntimeError, "closed"):
            self._begin()

    def _begin(self):
        return self.ledger.begin_turn(
            input_mode=VoiceInputMode.PUSH_TO_TALK,
            processing_mode=VoiceProcessingMode.LOCAL_MODULAR,
        )

    @staticmethod
    def _partial(turn, revision_number: int) -> TranscriptRevision:
        return TranscriptRevision(
            session_id=turn.session_id,
            turn_id=turn.turn_id,
            revision_number=revision_number,
            text=f"Partial {revision_number}",
            status=TranscriptStatus.PARTIAL,
            provider_name="fake",
        )

    @staticmethod
    def _final(turn, revision_number: int, text: str) -> TranscriptRevision:
        return TranscriptRevision(
            session_id=turn.session_id,
            turn_id=turn.turn_id,
            revision_number=revision_number,
            text=text,
            status=TranscriptStatus.FINAL,
            provider_name="fake",
            endpoint_reason=EndpointReason.SILENCE,
        )


if __name__ == "__main__":
    unittest.main()
