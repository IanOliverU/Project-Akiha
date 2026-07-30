from __future__ import annotations

import unittest

from project_akiha.core.behavior import CompanionMood
from project_akiha.services.speech_identity import (
    AKIHA_SPEECH_IDENTITY,
    AkihaSpeechStyleService,
    build_akiha_identity_system_prompt,
)


class AkihaSpeechIdentityTest(unittest.TestCase):
    """Verify minimal identity direction and speech-only formatting."""

    def test_provider_prompt_is_compact_and_idempotent(self) -> None:
        base = "Answer the user's question accurately."

        prompt = build_akiha_identity_system_prompt(base)
        repeated = build_akiha_identity_system_prompt(prompt)

        self.assertEqual(prompt, repeated)
        self.assertIn("natural Japanese", prompt)
        self.assertIn("formal, polite, refined", prompt)
        self.assertIn("Preserve facts, names, numbers", prompt)
        self.assertNotIn("Tsukihime", prompt)

    def test_profile_covers_required_scenarios_with_original_samples(self) -> None:
        scenarios = dict(AKIHA_SPEECH_IDENTITY.scenario_rules)
        samples = dict(AKIHA_SPEECH_IDENTITY.sample_phrases)

        self.assertEqual(
            set(scenarios),
            {
                "Normal conversation",
                "Concern",
                "Reminder",
                "Recoverable error",
                "Proactive check-in",
            },
        )
        self.assertEqual(
            set(samples),
            {"Normal", "Concern", "Reminder", "Error", "Proactive"},
        )

    def test_style_removes_markup_without_changing_facts(self) -> None:
        source = (
            "## ご案内\n"
            "- **会議**は14:30です。\n"
            "- [資料](https://example.test)を確認してください。"
        )

        styled = AkihaSpeechStyleService().style(source)

        self.assertEqual(
            styled.text,
            "ご案内\n会議は14:30です。\n資料を確認してください。",
        )
        self.assertEqual(styled.speaking_rate_multiplier, 1.0)

    def test_style_is_idempotent(self) -> None:
        service = AkihaSpeechStyleService()
        first = service.style("**承知しました。**")
        second = service.style(first.text)

        self.assertEqual(second.text, first.text)

    def test_resting_mood_uses_more_measured_delivery(self) -> None:
        styled = AkihaSpeechStyleService().style(
            "少し休みましょう。",
            CompanionMood.RESTING,
        )

        self.assertEqual(styled.speaking_rate_multiplier, 0.94)

    def test_empty_text_is_rejected_for_caller_fallback(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-empty"):
            AkihaSpeechStyleService().style(" ")


if __name__ == "__main__":
    unittest.main()
