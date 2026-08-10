"""Coordinate immediate local cancellation with hosted provider barge-in."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Protocol

from project_akiha.core.voice_session import (
    ConversationTurn,
    TurnInterruptionState,
    VoiceInputMode,
)


class _HostedLiveAdapter(Protocol):
    async def interrupt(self, turn_id: str) -> None:
        """Request provider-native interruption for one owned turn."""


class _TurnCoordinator(Protocol):
    @property
    def snapshot(self):
        """Return the current session snapshot."""

    def replace_turn(self, input_mode: VoiceInputMode) -> ConversationTurn:
        """Interrupt the active turn and return its replacement."""

    def get_turn(self, turn_id: str) -> ConversationTurn | None:
        """Return one historical turn without restoring authority."""

    def report_error(self, code: str):
        """End active turn ownership after an unrecoverable provider failure."""


class _TranscriptOwner(Protocol):
    def cancel_turn(self, turn_id: str) -> bool:
        """Discard interrupted transcript state."""

    def start_turn(self, *, session_id: str, turn_id: str) -> None:
        """Transfer transcript ownership to the replacement turn."""


class _PlaybackOwner(Protocol):
    def cancel(self) -> None:
        """Stop native playback and discard all queued response audio."""


@dataclass(frozen=True, slots=True)
class HostedLiveInterruptionResult:
    """One locally completed interruption awaiting provider reconciliation."""

    interrupted_turn_id: str
    replacement_turn: ConversationTurn
    provider_confirmation_pending: bool = True


class HostedLiveInterruptionController:
    """Make local cancellation immediate while Gemini confirms asynchronously."""

    def __init__(
        self,
        adapter: _HostedLiveAdapter,
        coordinator: _TurnCoordinator,
        transcripts: _TranscriptOwner,
        playback: _PlaybackOwner,
    ) -> None:
        self._adapter = adapter
        self._coordinator = coordinator
        self._transcripts = transcripts
        self._playback = playback
        self._lock = threading.RLock()
        self._pending_confirmation_turn_id: str | None = None

    @property
    def pending_confirmation_turn_id(self) -> str | None:
        with self._lock:
            return self._pending_confirmation_turn_id

    async def interrupt_and_replace(
        self,
        input_mode: VoiceInputMode = VoiceInputMode.HOSTED_LIVE_CONVERSATION,
    ) -> HostedLiveInterruptionResult:
        """Cancel old local output, transfer ownership, then signal Gemini."""
        active_turn = self._coordinator.snapshot.active_turn
        if active_turn is None:
            raise RuntimeError("No hosted live turn is available to interrupt.")
        with self._lock:
            if self._pending_confirmation_turn_id is not None:
                raise RuntimeError("A provider interruption is already pending.")

        if not self._transcripts.cancel_turn(active_turn.turn_id):
            raise RuntimeError("The interrupted transcript turn was not owned.")
        self._playback.cancel()
        replacement = self._coordinator.replace_turn(input_mode)
        self._transcripts.start_turn(
            session_id=replacement.session_id,
            turn_id=replacement.turn_id,
        )
        with self._lock:
            self._pending_confirmation_turn_id = active_turn.turn_id

        try:
            await self._adapter.interrupt(active_turn.turn_id)
        except Exception:
            with self._lock:
                self._pending_confirmation_turn_id = None
            self._transcripts.cancel_turn(replacement.turn_id)
            self._coordinator.report_error("provider_interruption_failed")
            raise
        return HostedLiveInterruptionResult(
            interrupted_turn_id=active_turn.turn_id,
            replacement_turn=replacement,
        )

    def provider_interruption_confirmed(self, turn_id: str) -> bool:
        """Reconcile only the provider confirmation for the interrupted turn."""
        with self._lock:
            if turn_id != self._pending_confirmation_turn_id:
                return False
            historical = self._coordinator.get_turn(turn_id)
            if (
                historical is None
                or historical.interruption is not TurnInterruptionState.INTERRUPTED
            ):
                return False
            self._pending_confirmation_turn_id = None
            return True
