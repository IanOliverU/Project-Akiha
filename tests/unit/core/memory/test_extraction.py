"""Tests for heuristic memory extraction."""

from __future__ import annotations

import unittest

from project_akiha.core.memory.extraction import HeuristicMemoryExtractor
from project_akiha.providers.ai import ChatMessage


class HeuristicMemoryExtractorTest(unittest.TestCase):
    """Verify deterministic memory candidate extraction."""

    def test_extracts_explicit_remember_request(self) -> None:
        extractor = HeuristicMemoryExtractor()

        candidates = extractor.extract(
            (ChatMessage(role="user", content="Please remember that I use Krita."),)
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].content, "I use Krita")
        self.assertEqual(candidates[0].importance, 4)
        self.assertEqual(candidates[0].tags, ("explicit",))

    def test_extracts_preference_statement(self) -> None:
        extractor = HeuristicMemoryExtractor()

        candidates = extractor.extract(
            (ChatMessage(role="user", content="I prefer concise replies."),)
        )

        self.assertEqual(candidates[0].content, "User prefers concise replies")
        self.assertEqual(candidates[0].tags, ("preference",))

    def test_extracts_identity_statement(self) -> None:
        extractor = HeuristicMemoryExtractor()

        candidates = extractor.extract(
            (ChatMessage(role="user", content="My name is Yuki."),)
        )

        self.assertEqual(candidates[0].content, "User's name is Yuki")
        self.assertEqual(candidates[0].importance, 5)
        self.assertEqual(candidates[0].tags, ("identity",))

    def test_ignores_assistant_messages(self) -> None:
        extractor = HeuristicMemoryExtractor()

        candidates = extractor.extract(
            (ChatMessage(role="assistant", content="Remember that this is generated."),)
        )

        self.assertEqual(candidates, ())

    def test_extracts_japanese_explicit_remember_request(self) -> None:
        extractor = HeuristicMemoryExtractor()

        candidates = extractor.extract(
            (
                ChatMessage(
                    role="user",
                    content="覚えておいて、私はKritaを使います。",
                ),
            )
        )

        self.assertEqual(candidates[0].content, "私はKritaを使います")
        self.assertEqual(candidates[0].tags, ("explicit",))

    def test_extracts_japanese_identity_statement(self) -> None:
        extractor = HeuristicMemoryExtractor()

        candidates = extractor.extract(
            (ChatMessage(role="user", content="私の名前はユキです。"),)
        )

        self.assertEqual(candidates[0].content, "ユーザーの名前はユキです")
        self.assertEqual(candidates[0].tags, ("identity",))

    def test_extracts_japanese_preference_statement(self) -> None:
        extractor = HeuristicMemoryExtractor()

        candidates = extractor.extract(
            (ChatMessage(role="user", content="私は紅茶が好きです。"),)
        )

        self.assertEqual(candidates[0].content, "ユーザーは紅茶が好きです")
        self.assertEqual(candidates[0].tags, ("preference",))

    def test_extracts_japanese_formal_preference_statement(self) -> None:
        extractor = HeuristicMemoryExtractor()

        candidates = extractor.extract(
            (ChatMessage(role="user", content="私は静かな場所を好みます。"),)
        )

        self.assertEqual(candidates[0].content, "ユーザーは静かな場所が好きです")
        self.assertEqual(candidates[0].tags, ("preference",))


if __name__ == "__main__":
    unittest.main()
