"""Tests for non-blocking assistant subtitle coordination."""

from __future__ import annotations

import unittest
from collections.abc import Callable

from project_akiha.app.assistant_translation_controller import (
    AssistantTranslationController,
)
from project_akiha.config import VoiceConfig


class AssistantTranslationControllerTest(unittest.TestCase):
    """Verify opt-in, fallback, cancellation, and late-result handling."""

    def test_disabled_subtitles_do_not_start_translation(self) -> None:
        controller, surface, threads = _build(VoiceConfig())

        started = controller.translate_assistant_response("こんにちは。")

        self.assertFalse(started)
        self.assertEqual(threads, [])
        self.assertEqual(surface.translations, [])

    def test_success_displays_translation_separately(self) -> None:
        controller, surface, threads = _build(
            VoiceConfig(english_subtitles_enabled=True),
            message_id=42,
        )

        started = controller.translate_assistant_response("こんにちは。")
        threads[0].translation_ready.emit("Hello.")

        self.assertTrue(started)
        self.assertEqual(surface.translations, ["Hello."])
        self.assertEqual(surface.unavailable_count, 0)
        self.assertEqual(threads[0].message_id, 42)

    def test_failure_uses_quiet_fallback_without_logging_source(self) -> None:
        controller, surface, threads = _build(
            VoiceConfig(english_subtitles_enabled=True)
        )
        source = "個人的な返答です。"

        with self.assertLogs("project_akiha.voice.translation", "WARNING") as logs:
            controller.translate_assistant_response(source)
            threads[0].translation_failed.emit("ProviderError")

        self.assertEqual(surface.translations, [])
        self.assertEqual(surface.unavailable_count, 1)
        self.assertNotIn(source, " ".join(logs.output))

    def test_disabling_subtitles_discards_late_result(self) -> None:
        controller, surface, threads = _build(
            VoiceConfig(english_subtitles_enabled=True)
        )
        controller.translate_assistant_response("こんにちは。")

        controller.apply_config(VoiceConfig(english_subtitles_enabled=False))
        threads[0].translation_ready.emit("Late result.")

        self.assertTrue(threads[0].cancelled)
        self.assertEqual(surface.translations, [])

    def test_cancel_reports_unfinished_worker_and_discards_result(self) -> None:
        controller, surface, threads = _build(
            VoiceConfig(english_subtitles_enabled=True),
            thread_finished=False,
        )
        controller.translate_assistant_response("こんにちは。")

        stopped = controller.cancel(wait_ms=25)
        threads[0].translation_ready.emit("Late result.")

        self.assertFalse(stopped)
        self.assertEqual(threads[0].wait_ms, 25)
        self.assertEqual(surface.translations, [])


class _Signal:
    def __init__(self) -> None:
        self.handlers: list[Callable[..., None]] = []

    def connect(self, handler: Callable[..., None]) -> None:
        self.handlers.append(handler)

    def emit(self, *args: object) -> None:
        for handler in tuple(self.handlers):
            handler(*args)


class _Thread:
    def __init__(self, *, finished: bool) -> None:
        self.translation_ready = _Signal()
        self.translation_failed = _Signal()
        self.translation_cancelled = _Signal()
        self.finished = _Signal()
        self.finished_result = finished
        self.started = False
        self.cancelled = False
        self.wait_ms = 0
        self.deleted = False
        self.message_id: int | None = None

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True

    def wait(self, time: int = 0) -> bool:
        self.wait_ms = time
        return self.finished_result

    def deleteLater(self) -> None:
        self.deleted = True


class _Surface:
    def __init__(self) -> None:
        self.translations: list[str] = []
        self.unavailable_count = 0

    def append_assistant_translation(self, content: str) -> None:
        self.translations.append(content)

    def append_translation_unavailable(self) -> None:
        self.unavailable_count += 1


def _build(
    config: VoiceConfig,
    *,
    thread_finished: bool = True,
    message_id: int | None = None,
) -> tuple[AssistantTranslationController, _Surface, list[_Thread]]:
    threads: list[_Thread] = []

    def build_thread(
        service: object,
        text: str,
        message_id: int | None,
    ) -> _Thread:
        del service, text
        thread = _Thread(finished=thread_finished)
        thread.message_id = message_id
        threads.append(thread)
        return thread

    surface = _Surface()
    controller = AssistantTranslationController(
        service=object(),
        surface=surface,
        config=config,
        thread_factory=build_thread,
        message_id_provider=lambda: message_id,
    )
    return controller, surface, threads


if __name__ == "__main__":
    unittest.main()
