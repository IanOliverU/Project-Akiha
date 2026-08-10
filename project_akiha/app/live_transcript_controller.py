"""Accept hosted-live transcript revisions before canonical chat persistence."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Protocol

from project_akiha.app.chat_controller import (
    CanonicalLiveChatCommit,
    ChatController,
)
from project_akiha.core.voice_session import (
    AssistantTextRevision,
    TranscriptRevision,
    TranscriptStatus,
)


@dataclass(frozen=True, slots=True)
class LiveTranscriptSnapshot:
    """Immutable transcript authority for one hosted-live turn."""

    session_id: str
    turn_id: str
    latest_input_revision: int = -1
    latest_assistant_revision: int = -1
    final_user_text: str | None = None
    final_assistant_text: str | None = None
    provider_turn_complete: bool = False
    committing: bool = False
    committed: bool = False
    commit_failed: bool = False


InputRevisionCallback = Callable[[TranscriptRevision], None]
AssistantRevisionCallback = Callable[[AssistantTextRevision], None]


class TranscriptRevisionAuthority(Protocol):
    """Existing turn ledger boundary that accepts canonical input revisions."""

    def accept_transcript_revision(self, revision: TranscriptRevision) -> bool:
        """Return whether the active voice turn accepts this revision."""


class LiveTranscriptController:
    """Keep partials ephemeral and commit only accepted final transcript text."""

    def __init__(
        self,
        chat_controller: ChatController,
        transcript_authority: TranscriptRevisionAuthority,
        *,
        on_input_revision: InputRevisionCallback | None = None,
        on_assistant_revision: AssistantRevisionCallback | None = None,
    ) -> None:
        self._chat_controller = chat_controller
        self._transcript_authority = transcript_authority
        self._on_input_revision = on_input_revision
        self._on_assistant_revision = on_assistant_revision
        self._lock = threading.RLock()
        self._snapshot: LiveTranscriptSnapshot | None = None

    @property
    def snapshot(self) -> LiveTranscriptSnapshot | None:
        with self._lock:
            return self._snapshot

    def start_turn(self, *, session_id: str, turn_id: str) -> None:
        """Begin one transcript authority after the voice coordinator starts a turn."""
        if not session_id.strip() or not turn_id.strip():
            raise ValueError("Live transcript IDs cannot be blank.")
        with self._lock:
            current = self._snapshot
            if current is not None and not (current.committed or current.commit_failed):
                raise RuntimeError("A live transcript turn is already active.")
            self._snapshot = LiveTranscriptSnapshot(
                session_id=session_id,
                turn_id=turn_id,
            )

    def transcript_revised(self, revision: TranscriptRevision) -> bool:
        """Accept a newer input revision and project it without persistence."""
        with self._lock:
            current = self._owned_snapshot(revision.session_id, revision.turn_id)
            if (
                current is None
                or current.committing
                or current.committed
                or current.commit_failed
            ):
                return False
            if current.final_user_text is not None:
                return False
            if revision.revision_number <= current.latest_input_revision:
                return False
            if not self._transcript_authority.accept_transcript_revision(revision):
                return False
            self._snapshot = replace(
                current,
                latest_input_revision=revision.revision_number,
                final_user_text=(
                    revision.text.strip()
                    if revision.status is TranscriptStatus.FINAL
                    else None
                ),
            )
        callback = self._on_input_revision
        if callback is not None:
            callback(revision)
        return True

    def assistant_text_revised(self, revision: AssistantTextRevision) -> bool:
        """Accept newer canonical assistant text while keeping partials ephemeral."""
        with self._lock:
            current = self._owned_snapshot(revision.session_id, revision.turn_id)
            if (
                current is None
                or current.committing
                or current.committed
                or current.commit_failed
            ):
                return False
            if current.final_assistant_text is not None:
                return False
            if revision.revision_number <= current.latest_assistant_revision:
                return False
            self._snapshot = replace(
                current,
                latest_assistant_revision=revision.revision_number,
                final_assistant_text=(
                    revision.text.strip() if revision.is_final else None
                ),
            )
        callback = self._on_assistant_revision
        if callback is not None:
            callback(revision)
        return True

    def turn_completed(self, turn_id: str) -> bool:
        """Record provider completion without assuming transcripts arrived first."""
        with self._lock:
            current = self._snapshot
            if (
                current is None
                or current.turn_id != turn_id
                or current.committing
                or current.committed
                or current.commit_failed
            ):
                return False
            self._snapshot = replace(current, provider_turn_complete=True)
            return True

    async def commit_completed_turn(
        self,
        turn_id: str,
        *,
        allow_audio_only: bool = False,
    ) -> CanonicalLiveChatCommit | None:
        """Commit one completed turn exactly once when canonical finals are ready."""
        with self._lock:
            current = self._snapshot
            if (
                current is None
                or current.turn_id != turn_id
                or current.committing
                or current.committed
                or current.commit_failed
                or not current.provider_turn_complete
                or current.final_user_text is None
                or (current.final_assistant_text is None and not allow_audio_only)
            ):
                return None
            self._snapshot = replace(current, committing=True)

        try:
            committed = await self._chat_controller.commit_canonical_live_turn(
                current.final_user_text,
                current.final_assistant_text,
            )
        except Exception:
            with self._lock:
                latest = self._snapshot
                if latest is not None and latest.turn_id == turn_id:
                    self._snapshot = replace(
                        latest,
                        committing=False,
                        commit_failed=True,
                    )
            raise

        with self._lock:
            latest = self._snapshot
            if latest is not None and latest.turn_id == turn_id:
                self._snapshot = replace(
                    latest,
                    committing=False,
                    committed=True,
                )
        return committed

    def cancel_turn(self, turn_id: str) -> bool:
        """Discard all partial and final text for an uncommitted interrupted turn."""
        with self._lock:
            current = self._snapshot
            if (
                current is None
                or current.turn_id != turn_id
                or current.committing
                or current.committed
                or current.commit_failed
            ):
                return False
            self._snapshot = None
            return True

    def _owned_snapshot(
        self,
        session_id: str,
        turn_id: str,
    ) -> LiveTranscriptSnapshot | None:
        current = self._snapshot
        if current is None:
            return None
        if (current.session_id, current.turn_id) != (session_id, turn_id):
            return None
        return current
