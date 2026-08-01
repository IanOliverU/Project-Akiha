"""Tests for completed canonical-response derived-output coordination."""

from __future__ import annotations

import unittest

from project_akiha.app.response_completion_controller import (
    ResponseCompletionController,
)


class ResponseCompletionControllerTest(unittest.TestCase):
    def test_streamed_speech_skips_whole_reply_but_translates_canonical_text(
        self,
    ) -> None:
        speech = _Speech()
        translation = _Translation()
        controller = ResponseCompletionController(speech, translation)
        canonical = "**\u627f\u77e5\u3057\u307e\u3057\u305f\u3002**"

        result = controller.complete(canonical, streaming_speech_started=True)

        self.assertFalse(result.fallback_speech_submitted)
        self.assertTrue(result.subtitle_requested)
        self.assertEqual(speech.received, [])
        self.assertEqual(translation.received, [canonical])

    def test_non_streamed_response_keeps_existing_full_reply_fallback(self) -> None:
        speech = _Speech()
        translation = _Translation()
        controller = ResponseCompletionController(speech, translation)

        result = controller.complete(
            "  One completed response.  ",
            streaming_speech_started=False,
        )

        self.assertTrue(result.fallback_speech_submitted)
        self.assertTrue(result.subtitle_requested)
        self.assertEqual(speech.received, ["One completed response."])
        self.assertEqual(translation.received, ["One completed response."])

    def test_empty_completion_never_starts_derived_output(self) -> None:
        speech = _Speech()
        translation = _Translation()
        controller = ResponseCompletionController(speech, translation)

        result = controller.complete(" ", streaming_speech_started=False)

        self.assertFalse(result.fallback_speech_submitted)
        self.assertFalse(result.subtitle_requested)
        self.assertEqual(speech.received, [])
        self.assertEqual(translation.received, [])


class _Speech:
    def __init__(self) -> None:
        self.received: list[str] = []

    def submit_assistant_reply(self, text: str) -> bool:
        self.received.append(text)
        return True


class _Translation:
    def __init__(self) -> None:
        self.received: list[str] = []

    def translate_assistant_response(self, text: str) -> bool:
        self.received.append(text)
        return True


if __name__ == "__main__":
    unittest.main()
