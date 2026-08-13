"""Tests for immediate hosted-live transcript presentation."""

from __future__ import annotations

import unittest

from project_akiha.app.chat_controller import CanonicalLiveChatCommit
from project_akiha.app.hosted_live_chat_presenter import HostedLiveChatPresenter
from project_akiha.core.voice_session import (
    AssistantTextRevision,
    EndpointReason,
    TranscriptRevision,
    TranscriptStatus,
)
from project_akiha.providers.ai import ChatMessage


class HostedLiveChatPresenterTest(unittest.TestCase):
    def test_projects_revisions_without_commit_duplicates(self) -> None:
        surface = _Surface()
        translated: list[str] = []
        presenter = HostedLiveChatPresenter(
            surface,
            assistant_name="Akiha",
            on_assistant_committed=translated.append,
        )

        presenter.input_revised(_input(0, "Hello", is_final=False))
        presenter.input_revised(_input(1, "Hello Akiha", is_final=True))
        presenter.assistant_revised(_assistant(0, "Good", is_final=False))
        presenter.assistant_revised(_assistant(1, "Good afternoon.", is_final=True))
        presenter.committed(
            "turn-1",
            CanonicalLiveChatCommit(
                user_message=ChatMessage(role="user", content="Hello Akiha"),
                assistant_message=ChatMessage(
                    role="assistant",
                    content="Good afternoon.",
                ),
            ),
        )

        self.assertEqual(
            surface.messages,
            [("You", "Hello Akiha"), ("Akiha", "Good afternoon.")],
        )
        self.assertEqual(translated, ["Good afternoon."])

    def test_commit_fills_missing_provider_output_transcript(self) -> None:
        surface = _Surface()
        presenter = HostedLiveChatPresenter(surface, assistant_name="Akiha")

        presenter.committed(
            "turn-1",
            CanonicalLiveChatCommit(
                user_message=ChatMessage(role="user", content="Hello"),
                assistant_message=ChatMessage(role="assistant", content="Hello."),
            ),
        )

        self.assertEqual(
            surface.messages,
            [("You", "Hello"), ("Akiha", "Hello.")],
        )


class _Surface:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []
        self._stream: tuple[str, str] | None = None

    def append_message(self, speaker: str, content: str) -> None:
        self.messages.append((speaker, content))

    def begin_streaming_message(self, speaker: str) -> None:
        self._stream = (speaker, "")

    def replace_streaming_message(self, speaker: str, content: str) -> None:
        self._stream = (speaker, content)

    def finish_streaming_message(self) -> None:
        if self._stream is not None:
            self.messages.append(self._stream)
            self._stream = None


def _input(revision: int, text: str, *, is_final: bool) -> TranscriptRevision:
    return TranscriptRevision(
        session_id="session-1",
        turn_id="turn-1",
        revision_number=revision,
        text=text,
        status=TranscriptStatus.FINAL if is_final else TranscriptStatus.PARTIAL,
        provider_name="gemini-live",
        endpoint_reason=EndpointReason.PROVIDER_FINAL if is_final else None,
    )


def _assistant(
    revision: int,
    text: str,
    *,
    is_final: bool,
) -> AssistantTextRevision:
    return AssistantTextRevision(
        session_id="session-1",
        turn_id="turn-1",
        revision_number=revision,
        text=text,
        is_final=is_final,
    )


if __name__ == "__main__":
    unittest.main()
