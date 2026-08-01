"""Tests for safe speech identity rendering of canonical response segments."""

from __future__ import annotations

import unittest

from project_akiha.core.behavior import CompanionMood
from project_akiha.core.voice_session import CanonicalResponseSegment
from project_akiha.services.response_segment_renderer import (
    ResponseSegmentRenderer,
    SafeSpeechStyleRenderer,
)
from project_akiha.services.speech_identity import StyledSpeech


class ResponseSegmentRendererTest(unittest.TestCase):
    def test_renders_speech_copy_without_mutating_canonical_text(self) -> None:
        class StyleService:
            def style(self, text: str, mood: CompanionMood | None) -> StyledSpeech:
                self.received = (text, mood)
                return StyledSpeech("Spoken copy.", 0.94)

        style = StyleService()
        renderer = ResponseSegmentRenderer(
            SafeSpeechStyleRenderer(style),
            mood_provider=lambda: CompanionMood.RESTING,
        )
        canonical = _segment("**Canonical copy.**", is_final=True)

        rendered = renderer.render(canonical)

        self.assertEqual(canonical.canonical_text, "**Canonical copy.**")
        self.assertEqual(rendered.canonical_text, canonical.canonical_text)
        self.assertEqual(rendered.speech_text, "Spoken copy.")
        self.assertEqual(rendered.speaking_rate_multiplier, 0.94)
        self.assertTrue(rendered.is_final)
        self.assertEqual(
            style.received,
            ("**Canonical copy.**", CompanionMood.RESTING),
        )

    def test_style_exception_falls_back_without_logging_private_text(self) -> None:
        class FailingStyleService:
            def style(self, text: str, mood: CompanionMood | None) -> StyledSpeech:
                del text, mood
                raise RuntimeError("private failure detail")

        renderer = ResponseSegmentRenderer(
            SafeSpeechStyleRenderer(FailingStyleService())
        )

        with self.assertLogs("project_akiha.voice.identity", "WARNING") as logs:
            rendered = renderer.render(_segment("Private canonical response."))

        self.assertEqual(rendered.speech_text, "Private canonical response.")
        logged = " ".join(logs.output)
        self.assertNotIn("Private canonical response", logged)
        self.assertNotIn("private failure detail", logged)

    def test_invalid_style_result_falls_back_to_canonical_text(self) -> None:
        class InvalidStyleService:
            def style(self, text: str, mood: CompanionMood | None) -> StyledSpeech:
                del text, mood
                return StyledSpeech(" ", 1.0)

        renderer = ResponseSegmentRenderer(
            SafeSpeechStyleRenderer(InvalidStyleService())
        )

        with self.assertLogs("project_akiha.voice.identity", "WARNING"):
            rendered = renderer.render(_segment("Fallback response."))

        self.assertEqual(rendered.speech_text, "Fallback response.")


def _segment(
    text: str,
    *,
    is_final: bool = False,
) -> CanonicalResponseSegment:
    return CanonicalResponseSegment(
        response_id="response-1",
        segment_index=0,
        canonical_text=text,
        is_final=is_final,
    )


if __name__ == "__main__":
    unittest.main()
