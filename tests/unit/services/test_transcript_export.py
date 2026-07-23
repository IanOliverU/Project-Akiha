"""Tests for plain-text chat transcript export."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.providers.ai import ChatMessage
from project_akiha.services.transcript_export import (
    render_chat_transcript,
    write_chat_transcript,
)


class TranscriptExportTest(unittest.TestCase):
    """Verify chat transcript rendering and writing."""

    def test_renders_user_and_assistant_messages(self) -> None:
        transcript = render_chat_transcript(
            (
                ChatMessage(role="system", content="hidden"),
                ChatMessage(role="user", content="hello"),
                ChatMessage(role="assistant", content="hi there"),
            ),
            assistant_name="Akiha",
        )

        self.assertEqual(transcript, "You: hello\n\nAkiha: hi there")

    def test_write_chat_transcript_creates_parent_directory(self) -> None:
        with TemporaryDirectory() as directory:
            export_path = Path(directory) / "exports" / "chat.txt"

            write_chat_transcript(export_path, "You: hello")

            self.assertEqual(export_path.read_text(encoding="utf-8"), "You: hello")


if __name__ == "__main__":
    unittest.main()
