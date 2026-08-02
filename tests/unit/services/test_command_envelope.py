"""Tests for conservative deterministic command-envelope extraction."""

from __future__ import annotations

import unittest

from project_akiha.services.command_envelope import (
    CommandEnvelopeRejection,
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
            ("Could you kindly open VLC for me?", "open VLC"),
            ("Would you be able to close Discord for me?", "close Discord"),
            ("Do me a favor and pause Spotify, please.", "pause Spotify"),
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

    def test_classifies_negated_commands_before_unwrapping(self) -> None:
        cases = (
            "Do not open Spotify.",
            "Please don't close Discord.",
            "Could you please not pause Spotify?",
            "Would you mind not opening Chrome?",
            "I don't want you to play Spotify.",
            "Never launch Visual Studio Code.",
        )

        for text in cases:
            with self.subTest(text=text):
                analysis = self.parser.analyze(text)

                self.assertIsNone(analysis.envelope)
                self.assertEqual(
                    analysis.rejection,
                    CommandEnvelopeRejection.NEGATED,
                )

    def test_classifies_metalinguistic_and_hypothetical_commands(self) -> None:
        cases = (
            "Tell me how to open Spotify.",
            "Could you explain why you opened Discord?",
            "Why did you open Spotify?",
            "Are you able to open Chrome?",
            "If I asked you to open Spotify, what would happen?",
            'The phrase "open Spotify" is one of your commands.',
            '"Open Spotify" is a command.',
            "I said open Spotify, not Discord.",
            "Repeat after me: open Spotify.",
        )

        for text in cases:
            with self.subTest(text=text):
                analysis = self.parser.analyze(text)

                self.assertIsNone(analysis.envelope)
                self.assertEqual(
                    analysis.rejection,
                    CommandEnvelopeRejection.METALINGUISTIC,
                )

    def test_target_words_do_not_trigger_anchored_guards(self) -> None:
        cases = (
            "Play Don't Start Now by Dua Lipa on Spotify.",
            "Play Never Enough by Loren Allred on Spotify.",
            "Search Spotify tracks for If I Could Fly by One Direction.",
        )

        for text in cases:
            with self.subTest(text=text):
                analysis = self.parser.analyze(text)

                self.assertIsNotNone(analysis.envelope)
                self.assertIsNone(analysis.rejection)


if __name__ == "__main__":
    unittest.main()
