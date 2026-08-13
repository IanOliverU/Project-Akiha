"""Present cumulative hosted-live transcripts without duplicate chat messages."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from project_akiha.app.chat_controller import CanonicalLiveChatCommit
from project_akiha.core.voice_session import (
    AssistantTextRevision,
    TranscriptRevision,
    TranscriptStatus,
)


class HostedLiveChatSurface(Protocol):
    """Small chat surface used by the hosted transcript presenter."""

    def append_message(self, speaker: str, content: str) -> None: ...

    def begin_streaming_message(self, speaker: str) -> None: ...

    def replace_streaming_message(self, speaker: str, content: str) -> None: ...

    def finish_streaming_message(self) -> None: ...


class HostedLiveChatPresenter:
    """Project live revisions immediately and reconcile canonical commits later."""

    def __init__(
        self,
        surface: HostedLiveChatSurface,
        *,
        assistant_name: str,
        on_assistant_committed: Callable[[str], None] | None = None,
    ) -> None:
        self._surface = surface
        self._assistant_name = assistant_name
        self._on_assistant_committed = on_assistant_committed
        self._active_stream: tuple[str, str] | None = None
        self._visible_user_turns: set[str] = set()
        self._visible_assistant_text: dict[str, str] = {}

    def input_revised(self, revision: TranscriptRevision) -> None:
        """Show cumulative microphone transcription as it arrives."""
        text = revision.text.strip()
        if not text:
            return
        self._replace_stream(revision.turn_id, "You", text)
        if revision.status is TranscriptStatus.FINAL:
            self._surface.finish_streaming_message()
            self._active_stream = None
            self._visible_user_turns.add(revision.turn_id)

    def assistant_revised(self, revision: AssistantTextRevision) -> None:
        """Show cumulative assistant speech transcription during playback."""
        text = revision.text.strip()
        if not text:
            return
        self._replace_stream(revision.turn_id, self._assistant_name, text)
        self._visible_assistant_text[revision.turn_id] = text
        if revision.is_final:
            self._surface.finish_streaming_message()
            self._active_stream = None

    def committed(self, turn_id: str, commit: CanonicalLiveChatCommit) -> None:
        """Fill missing final text without duplicating projected revisions."""
        if turn_id not in self._visible_user_turns:
            self._surface.append_message("You", commit.user_message.content)

        assistant_message = commit.assistant_message
        if assistant_message is not None:
            canonical_text = assistant_message.content
            visible_text = self._visible_assistant_text.get(turn_id)
            if visible_text != canonical_text:
                if self._active_stream == (turn_id, self._assistant_name):
                    self._surface.replace_streaming_message(
                        self._assistant_name,
                        canonical_text,
                    )
                    self._surface.finish_streaming_message()
                    self._active_stream = None
                else:
                    self._surface.append_message(
                        self._assistant_name,
                        canonical_text,
                    )
            callback = self._on_assistant_committed
            if callback is not None:
                callback(canonical_text)

        self._visible_user_turns.discard(turn_id)
        self._visible_assistant_text.pop(turn_id, None)

    def reset(self) -> None:
        """Discard ephemeral projection state after chat reset or shutdown."""
        self._active_stream = None
        self._visible_user_turns.clear()
        self._visible_assistant_text.clear()
        self._surface.finish_streaming_message()

    def _replace_stream(self, turn_id: str, speaker: str, text: str) -> None:
        stream = (turn_id, speaker)
        if self._active_stream != stream:
            if self._active_stream is not None:
                self._surface.finish_streaming_message()
            self._surface.begin_streaming_message(speaker)
            self._active_stream = stream
        self._surface.replace_streaming_message(speaker, text)
