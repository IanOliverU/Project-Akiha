"""Tests for conservative deterministic command-envelope extraction."""

from __future__ import annotations

import unittest

from project_akiha.services.command_envelope import (
    DeterministicCommandEnvelopeParser,
)


class DeterministicCommandEnvelopeParserTest(unittest.TestCase):
    """Verify natural wrappers are removed without interpreting targets."""

    def setUp(self) -> None:
        self.parser = DeterministicCommandEnvelopeParser()

    def test_preserves_direct_command_content(self) -> None:
        envelope = self.parser.parse("Open Spotify.")

        self.assertIsNotNone(envelope)
        self.assertEqual(envelope.command_text, "Open Spotify.")
        self.assertFalse(envelope.transformed)

    def test_preserves_direct_explicit_path_exactly(self) -> None:
        text = r"/open-file C:\Users\Akiha\Documents\notes.txt"

        envelope = self.parser.parse(text)

        self.assertIsNotNone(envelope)
        self.assertEqual(envelope.command_text, text)

    def test_removes_modal_and_courtesy_wrappers(self) -> None:
        cases = (
            ("Could you please open Spotify for me?", "open Spotify"),
            ("Please, could you just pause the music, please.", "pause the music"),
            ("Would it be possible for you to open Discord?", "open Discord"),
            ("I'd like you to resume Spotify right now.", "resume Spotify"),
        )

        for text, expected in cases:
            with self.subTest(text=text):
                envelope = self.parser.parse(text)

                self.assertIsNotNone(envelope)
                self.assertEqual(envelope.command_text, expected)
                self.assertTrue(envelope.transformed)

    def test_normalizes_supported_mind_gerund(self) -> None:
        envelope = self.parser.parse(
            "Would you mind opening the Spotify application for me?"
        )

        self.assertIsNotNone(envelope)
        self.assertEqual(envelope.command_text, "open the Spotify application")

    def test_does_not_extract_command_from_arbitrary_sentence(self) -> None:
        text = "I was thinking about whether opening Spotify would help."

        envelope = self.parser.parse(text)

        self.assertIsNotNone(envelope)
        self.assertEqual(
            envelope.command_text,
            "I was thinking about whether opening Spotify would help.",
        )

    def test_rejects_empty_and_oversized_input(self) -> None:
        self.assertIsNone(self.parser.parse("   "))
        self.assertIsNone(self.parser.parse("x" * 2_001))


if __name__ == "__main__":
    unittest.main()
