"""Plain-text chat transcript export."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from project_akiha.core.memory import MessageRole


class TranscriptMessage(Protocol):
    """Message shape accepted by the transcript exporter."""

    role: MessageRole
    content: str


def render_chat_transcript(
    messages: Sequence[TranscriptMessage],
    assistant_name: str,
) -> str:
    """Render chat messages as a plain-text transcript."""
    lines: list[str] = []
    for message in messages:
        speaker = _speaker_for_role(message.role, assistant_name)
        if speaker is None:
            continue

        lines.append(f"{speaker}: {message.content}")

    return "\n\n".join(lines)


def write_chat_transcript(path: Path, transcript: str) -> None:
    """Write a rendered transcript to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(transcript, encoding="utf-8")


def _speaker_for_role(role: MessageRole, assistant_name: str) -> str | None:
    if role == "user":
        return "You"
    if role == "assistant":
        return assistant_name
    return None
