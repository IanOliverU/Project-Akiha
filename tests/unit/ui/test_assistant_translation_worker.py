"""Tests for the Qt assistant translation worker."""

from __future__ import annotations

import unittest

from project_akiha.ui.assistant_translation_worker import (
    AssistantTranslationThread,
)


class AssistantTranslationThreadTest(unittest.TestCase):
    """Verify worker success, failure privacy, and cancellation."""

    def test_emits_successful_translation(self) -> None:
        thread = AssistantTranslationThread(_Service("Hello."), "こんにちは。")
        translations: list[str] = []
        thread.translation_ready.connect(translations.append)

        thread.run()

        self.assertEqual(translations, ["Hello."])

    def test_failure_emits_only_exception_type(self) -> None:
        thread = AssistantTranslationThread(
            _Service(error=RuntimeError("private source")),
            "個人的な返答です。",
        )
        failures: list[str] = []
        thread.translation_failed.connect(failures.append)

        thread.run()

        self.assertEqual(failures, ["RuntimeError"])

    def test_cancelled_worker_discards_translation(self) -> None:
        thread = AssistantTranslationThread(_Service("Late result."), "こんにちは。")
        translations: list[str] = []
        cancelled: list[bool] = []
        thread.translation_ready.connect(translations.append)
        thread.translation_cancelled.connect(lambda: cancelled.append(True))

        thread.cancel()
        thread.run()

        self.assertEqual(translations, [])
        self.assertEqual(cancelled, [True])


class _Service:
    def __init__(
        self,
        response: str = "",
        *,
        error: Exception | None = None,
    ) -> None:
        self._response = response
        self._error = error

    async def translate_to_english(self, text: str) -> str:
        del text
        if self._error is not None:
            raise self._error
        return self._response


if __name__ == "__main__":
    unittest.main()
