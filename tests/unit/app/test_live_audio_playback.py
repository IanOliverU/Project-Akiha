"""Tests for native Gemini audio reuse of the existing playback owner."""

from __future__ import annotations

import unittest

from project_akiha.app.live_audio_playback import NativeAudioPlaybackQueue
from project_akiha.core.voice_session import (
    AudioFrame,
    LiveSessionError,
    LiveSessionErrorCode,
)
from project_akiha.providers.voice import SynthesizedAudio


class NativeAudioPlaybackQueueTest(unittest.TestCase):
    def test_plays_ordered_segments_through_one_existing_owner(self) -> None:
        owner = _PlaybackOwner()
        completed: list[bool] = []
        queue = NativeAudioPlaybackQueue(
            owner,
            segment_duration_ms=100,
            maximum_queued_segments=3,
        )
        queue.start_turn(
            session_id="session-1",
            turn_id="turn-1",
            on_complete=lambda: completed.append(True),
        )

        queue.submit(_frame(sequence=0))
        queue.submit(_frame(sequence=1))
        queue.finish_turn()

        self.assertEqual(len(owner.played), 1)
        self.assertEqual(queue.queued_segment_count, 2)
        owner.finish()
        self.assertEqual(len(owner.played), 2)
        owner.finish()
        self.assertEqual(completed, [True])
        self.assertFalse(queue.is_active)

    def test_backpressure_stops_owner_and_discards_queue(self) -> None:
        owner = _PlaybackOwner()
        queue = NativeAudioPlaybackQueue(
            owner,
            segment_duration_ms=100,
            maximum_queued_segments=1,
        )
        queue.start_turn(session_id="session-1", turn_id="turn-1")
        queue.submit(_frame(sequence=0))

        with self.assertRaises(LiveSessionError) as captured:
            queue.submit(_frame(sequence=1))

        self.assertEqual(
            captured.exception.code,
            LiveSessionErrorCode.AUDIO_BACKPRESSURE,
        )
        self.assertTrue(owner.cancelled)
        self.assertFalse(queue.is_active)

    def test_cancel_rejects_late_playback_callback(self) -> None:
        owner = _PlaybackOwner()
        completed: list[bool] = []
        queue = NativeAudioPlaybackQueue(owner, segment_duration_ms=100)
        queue.start_turn(
            session_id="session-1",
            turn_id="turn-1",
            on_complete=lambda: completed.append(True),
        )
        queue.submit(_frame())
        stale_finished = owner.on_finished

        queue.cancel()
        stale_finished()

        self.assertEqual(completed, [])
        self.assertFalse(queue.is_active)

    def test_synchronous_owner_failure_is_sanitized_and_releases_turn(self) -> None:
        owner = _PlaybackOwner(fail_on_play=True)
        failures: list[tuple[str, str]] = []
        queue = NativeAudioPlaybackQueue(owner, segment_duration_ms=100)
        queue.start_turn(
            session_id="session-1",
            turn_id="turn-1",
            on_error=lambda code, message: failures.append((code, message)),
        )

        queue.submit(_frame())

        self.assertEqual(
            failures,
            [
                (
                    "native_playback_failed",
                    "Native speech playback could not start.",
                )
            ],
        )
        self.assertFalse(queue.is_active)


class _PlaybackOwner:
    def __init__(self, *, fail_on_play: bool = False) -> None:
        self.played: list[SynthesizedAudio] = []
        self.cancelled = False
        self.fail_on_play = fail_on_play
        self.on_finished = lambda: None
        self.on_error = lambda _code, _message: None

    def play(
        self,
        audio: SynthesizedAudio,
        *,
        recover_on_finish: bool = True,
        on_finished: object = None,
        on_error: object = None,
    ) -> None:
        self.assert_recover_disabled(recover_on_finish)
        if self.fail_on_play:
            raise RuntimeError("private device detail")
        self.played.append(audio)
        assert callable(on_finished) and callable(on_error)
        self.on_finished = on_finished
        self.on_error = on_error

    def cancel(self) -> None:
        self.cancelled = True

    def finish(self) -> None:
        callback = self.on_finished
        self.on_finished = lambda: None
        callback()

    @staticmethod
    def assert_recover_disabled(value: bool) -> None:
        if value:
            raise AssertionError("Native segments must retain shared output ownership.")


def _frame(*, sequence: int = 0) -> AudioFrame:
    return AudioFrame(
        session_id="session-1",
        turn_id="turn-1",
        sequence_number=sequence,
        captured_at_monotonic=sequence * 0.1,
        sample_rate_hz=24_000,
        channels=1,
        sample_width_bytes=2,
        data=b"\x00\x00" * 2_400,
    )


if __name__ == "__main__":
    unittest.main()
