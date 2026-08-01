"""Tests for ordered segment handoff to the existing Qt playback owner."""

from __future__ import annotations

import asyncio
import threading
import time
import unittest
from collections.abc import Coroutine
from typing import Any

from PySide6.QtWidgets import QApplication

from project_akiha.providers.voice import (
    AudioPlaybackError,
    SpeechSynthesisRequest,
    SynthesizedAudio,
    VoiceProviderHealth,
    VoiceProviderStatus,
)
from project_akiha.services.speech_output import SpeechOutputService
from spikes.voice_pipeline.pipeline_spike import ResponseSegment
from spikes.voice_pipeline.qt_playback_bridge import QtSegmentPlaybackBridge
from spikes.voice_pipeline.voicevox_processor import OrderedVoiceVoxProcessor


class QtSegmentPlaybackBridgeTest(unittest.TestCase):
    def test_ordered_processor_uses_one_owner_on_the_qt_thread(self) -> None:
        owner = _PlaybackOwner(auto_finish=True)
        bridge = QtSegmentPlaybackBridge(owner)
        main_thread_id = threading.get_ident()

        async def exercise() -> None:
            processor = OrderedVoiceVoxProcessor(
                SpeechOutputService(_ImmediateProvider()),
                maximum_concurrent_synthesis=2,
            )
            processor.start_turn(1, bridge)
            processor.submit(_segment(0, "First sentence."))
            processor.submit(_segment(1, "Second sentence."))
            processor.submit(_segment(2, "Third sentence."))
            await processor.finish_turn(1)

        _run_with_qt_events(exercise())

        self.assertEqual(
            owner.played,
            ["First sentence.", "Second sentence.", "Third sentence."],
        )
        self.assertEqual(owner.maximum_active, 1)
        self.assertEqual(owner.thread_ids, [main_thread_id] * 3)

    def test_cancelled_await_stops_the_qt_owner(self) -> None:
        owner = _PlaybackOwner(auto_finish=False)
        bridge = QtSegmentPlaybackBridge(owner)

        async def exercise() -> None:
            processor = OrderedVoiceVoxProcessor(
                SpeechOutputService(_ImmediateProvider())
            )
            processor.start_turn(1, bridge)
            processor.submit(_segment(0, "Long sentence."))
            await asyncio.to_thread(owner.started.wait, 1.0)
            self.assertTrue(await processor.cancel_turn(1))

        _run_with_qt_events(exercise())

        self.assertTrue(owner.stopped)
        self.assertEqual(owner.active, 0)

    def test_playback_error_returns_to_the_async_pipeline(self) -> None:
        owner = _PlaybackOwner(
            auto_finish=True,
            play_error=AudioPlaybackError(
                "output_device_unavailable",
                "No audio output device is available.",
            ),
        )
        bridge = QtSegmentPlaybackBridge(owner)

        async def exercise() -> None:
            with self.assertRaisesRegex(
                AudioPlaybackError,
                "No audio output device",
            ):
                await bridge.play(
                    _segment(0, "Hello."),
                    _audio("Hello."),
                )

        _run_with_qt_events(exercise())
        self.assertEqual(owner.active, 0)


class _ImmediateProvider:
    async def health(self) -> VoiceProviderHealth:
        return VoiceProviderHealth(VoiceProviderStatus.AVAILABLE)

    async def synthesize(self, request: SpeechSynthesisRequest) -> SynthesizedAudio:
        return _audio(request.text)

    async def available_voices(self) -> tuple[()]:
        return ()


class _PlaybackOwner:
    def __init__(
        self,
        *,
        auto_finish: bool,
        play_error: Exception | None = None,
    ) -> None:
        self.auto_finish = auto_finish
        self.play_error = play_error
        self.is_active = False
        self.active = 0
        self.maximum_active = 0
        self.played: list[str] = []
        self.thread_ids: list[int] = []
        self.started = threading.Event()
        self.stopped = False

    def apply_settings(self, device_name: str, volume_percent: int) -> None:
        del device_name, volume_percent

    def play(
        self,
        audio: SynthesizedAudio,
        *,
        on_started,
        on_finished,
        on_error,
    ) -> None:
        del on_error
        if self.play_error is not None:
            raise self.play_error
        self.is_active = True
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        self.played.append(audio.data.decode("utf-8"))
        self.thread_ids.append(threading.get_ident())
        self.started.set()
        on_started()
        if self.auto_finish:
            self.is_active = False
            self.active -= 1
            on_finished()

    def stop(self) -> None:
        self.stopped = True
        self.is_active = False
        self.active = 0


def _run_with_qt_events(coroutine: Coroutine[Any, Any, None]) -> None:
    app = QApplication.instance() or QApplication([])
    failures: list[BaseException] = []

    def run() -> None:
        try:
            asyncio.run(coroutine)
        except BaseException as error:
            failures.append(error)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    deadline = time.monotonic() + 5.0
    while worker.is_alive() and time.monotonic() < deadline:
        app.processEvents()
        worker.join(0.002)
    for _ in range(3):
        app.processEvents()
    worker.join(0.1)
    if worker.is_alive():
        raise TimeoutError("Qt playback bridge test did not finish.")
    if failures:
        raise failures[0]


def _segment(index: int, text: str) -> ResponseSegment:
    return ResponseSegment(turn_id=1, index=index, text=text)


def _audio(text: str) -> SynthesizedAudio:
    return SynthesizedAudio(text.encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
