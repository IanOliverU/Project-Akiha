"""Tests for deterministic conversation summarization."""

from __future__ import annotations

import unittest

from project_akiha.core.memory import HeuristicConversationSummarizer
from project_akiha.providers.ai import ChatMessage


class HeuristicConversationSummarizerTest(unittest.TestCase):
    """Verify closed conversation summary generation."""

    def test_summarizes_visible_user_topics(self) -> None:
        summarizer = HeuristicConversationSummarizer()

        summary = summarizer.summarize(
            (
                ChatMessage(role="system", content="hidden"),
                ChatMessage(role="user", content=" Remember that I use Krita. "),
                ChatMessage(role="assistant", content="Got it."),
                ChatMessage(role="user", content="Also I prefer concise replies."),
            )
        )

        self.assertIn("3 visible messages", summary)
        self.assertIn("2 user, 1 assistant", summary)
        self.assertIn("Remember that I use Krita.", summary)
        self.assertIn("Also I prefer concise replies.", summary)

    def test_returns_empty_summary_for_empty_conversation(self) -> None:
        summarizer = HeuristicConversationSummarizer()

        self.assertEqual(summarizer.summarize(()), "")

    def test_clips_long_user_points(self) -> None:
        summarizer = HeuristicConversationSummarizer(max_point_length=10)

        summary = summarizer.summarize(
            (ChatMessage(role="user", content="This is a very long topic."),)
        )

        self.assertIn("This is a...", summary)
