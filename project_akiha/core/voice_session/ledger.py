"""Thread-safe turn ownership and transcript revision authority."""

from __future__ import annotations

import threading
from dataclasses import replace

from project_akiha.core.voice_session.models import (
    CaptureStage,
    ConversationTurn,
    GenerationStage,
    PlaybackStage,
    RecognitionStage,
    SynthesisStage,
    TranscriptRevision,
    TranscriptStatus,
    TurnInterruptionState,
    VoiceCancellationToken,
    VoiceInputMode,
    VoiceProcessingMode,
)


class VoiceTurnLedger:
    """Own one active turn and reject stale or out-of-order callbacks."""

    def __init__(self, session_id: str) -> None:
        # ConversationTurn performs the shared identifier validation.
        self._session_id = session_id
        self._lock = threading.RLock()
        self._next_turn_number = 1
        self._active_turn_id: str | None = None
        self._turns: dict[str, ConversationTurn] = {}
        self._closed = False

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def active_turn(self) -> ConversationTurn | None:
        """Return the current immutable turn snapshot, if any."""
        with self._lock:
            if self._active_turn_id is None:
                return None
            return self._turns[self._active_turn_id]

    @property
    def is_closed(self) -> bool:
        with self._lock:
            return self._closed

    def begin_turn(
        self,
        *,
        input_mode: VoiceInputMode,
        processing_mode: VoiceProcessingMode,
    ) -> ConversationTurn:
        """Begin a turn only when no other turn owns callbacks."""
        with self._lock:
            if self._closed:
                raise RuntimeError("voice turn ledger is closed.")
            if self._active_turn_id is not None:
                raise RuntimeError("an active voice turn already exists.")
            return self._begin_turn(input_mode, processing_mode)

    def replace_turn(
        self,
        *,
        input_mode: VoiceInputMode,
        processing_mode: VoiceProcessingMode,
    ) -> ConversationTurn:
        """Interrupt the active turn, then transfer ownership to a new turn."""
        with self._lock:
            if self._closed:
                raise RuntimeError("voice turn ledger is closed.")
            self._cancel_active(interrupted=True)
            return self._begin_turn(input_mode, processing_mode)

    def accepts_callback(self, session_id: str, turn_id: str) -> bool:
        """Return whether a callback still belongs to the active turn."""
        with self._lock:
            if self._closed or session_id != self._session_id:
                return False
            if turn_id != self._active_turn_id:
                return False
            turn = self._turns[turn_id]
            return not turn.cancellation_token.is_cancelled

    def accept_transcript_revision(self, revision: TranscriptRevision) -> bool:
        """Accept only a newer revision belonging to the active turn."""
        with self._lock:
            if not self.accepts_callback(revision.session_id, revision.turn_id):
                return False

            turn = self._turns[revision.turn_id]
            if turn.accepted_final_transcript is not None:
                return False
            if revision.revision_number <= turn.latest_transcript_revision:
                return False

            recognition = (
                RecognitionStage.FINAL
                if revision.status is TranscriptStatus.FINAL
                else RecognitionStage.PARTIAL
            )
            accepted_final = (
                revision
                if revision.status is TranscriptStatus.FINAL
                else turn.accepted_final_transcript
            )
            updated_turn = replace(
                turn,
                stages=replace(turn.stages, recognition=recognition),
                accepted_final_transcript=accepted_final,
                latest_transcript_revision=revision.revision_number,
            )
            self._turns[revision.turn_id] = updated_turn
            return True

    def replace_active_stages(
        self,
        session_id: str,
        turn_id: str,
        stages,
    ) -> bool:
        """Replace stages only while the referenced turn owns callbacks."""
        with self._lock:
            if not self.accepts_callback(session_id, turn_id):
                return False
            turn = self._turns[turn_id]
            self._turns[turn_id] = replace(turn, stages=stages)
            return True

    def cancel_active(self) -> ConversationTurn | None:
        """Cancel the active turn without treating it as barge-in."""
        with self._lock:
            return self._cancel_active(interrupted=False)

    def complete_active(self) -> ConversationTurn | None:
        """Release callback ownership from the active turn."""
        with self._lock:
            if self._active_turn_id is None:
                return None
            turn = self._turns[self._active_turn_id]
            self._active_turn_id = None
            return turn

    def get_turn(self, turn_id: str) -> ConversationTurn | None:
        """Return an immutable historical snapshot without restoring authority."""
        with self._lock:
            return self._turns.get(turn_id)

    def close(self) -> None:
        """Cancel active work and permanently reject new turns and callbacks."""
        with self._lock:
            self._cancel_active(interrupted=False)
            self._closed = True

    def _begin_turn(
        self,
        input_mode: VoiceInputMode,
        processing_mode: VoiceProcessingMode,
    ) -> ConversationTurn:
        turn_id = str(self._next_turn_number)
        self._next_turn_number += 1
        turn = ConversationTurn(
            session_id=self._session_id,
            turn_id=turn_id,
            cancellation_token=VoiceCancellationToken(),
            input_mode=input_mode,
            processing_mode=processing_mode,
        )
        self._turns[turn_id] = turn
        self._active_turn_id = turn_id
        return turn

    def _cancel_active(self, *, interrupted: bool) -> ConversationTurn | None:
        if self._active_turn_id is None:
            return None
        turn = self._turns[self._active_turn_id]
        turn.cancellation_token.cancel()
        updated_turn = replace(
            turn,
            stages=_cancel_active_stages(turn),
            interruption=(
                TurnInterruptionState.INTERRUPTED
                if interrupted
                else TurnInterruptionState.CANCELLED
            ),
        )
        self._turns[turn.turn_id] = updated_turn
        self._active_turn_id = None
        return updated_turn


def _cancel_active_stages(turn: ConversationTurn):
    stages = turn.stages
    capture = (
        CaptureStage.CANCELLED
        if stages.capture in {CaptureStage.CAPTURING, CaptureStage.ENDPOINTING}
        else stages.capture
    )
    recognition = (
        RecognitionStage.CANCELLED
        if stages.recognition in {RecognitionStage.PARTIAL, RecognitionStage.FINALIZING}
        else stages.recognition
    )
    generation = (
        GenerationStage.CANCELLED
        if stages.generation is GenerationStage.STREAMING
        else stages.generation
    )
    synthesis = (
        SynthesisStage.CANCELLED
        if stages.synthesis in {SynthesisStage.QUEUED, SynthesisStage.ACTIVE}
        else stages.synthesis
    )
    playback = (
        PlaybackStage.CANCELLED
        if stages.playback in {PlaybackStage.BUFFERING, PlaybackStage.PLAYING}
        else stages.playback
    )
    return replace(
        stages,
        capture=capture,
        recognition=recognition,
        generation=generation,
        synthesis=synthesis,
        playback=playback,
    )
