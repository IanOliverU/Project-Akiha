"""Tests for cumulative microphone snapshot framing."""

from __future__ import annotations

import unittest

from project_akiha.app.voice_audio_bridge import (
    CumulativeAudioFrameBridge,
    RealtimeAudioFrameBridge,
)
from project_akiha.providers.voice import CapturedAudio


class CumulativeAudioFrameBridgeTest(unittest.TestCase):
    def test_emits_only_appended_pcm_as_bounded_ordered_frames(self) -> None:
        bridge = CumulativeAudioFrameBridge(
            maximum_frame_duration_ms=100,
            clock=iter((1.0, 2.0, 3.0)).__next__,
        )
        bridge.start_turn(session_id="session-1", turn_id="turn-1")

        first = bridge.accept_snapshot(_audio(bytes(4_000)))
        second = bridge.accept_snapshot(_audio(bytes(5_000)))

        self.assertEqual([len(frame.data) for frame in first], [3_200, 800])
        self.assertEqual([len(frame.data) for frame in second], [1_000])
        self.assertEqual(
            [frame.sequence_number for frame in (*first, *second)],
            [0, 1, 2],
        )
        self.assertTrue(
            all(
                (frame.session_id, frame.turn_id) == ("session-1", "turn-1")
                for frame in (*first, *second)
            )
        )

    def test_duplicate_snapshot_does_not_duplicate_frames(self) -> None:
        bridge = _bridge()
        audio = _audio(b"\x00\x01")
        bridge.accept_snapshot(audio)

        self.assertEqual(bridge.accept_snapshot(audio), ())

    def test_detects_backwards_mutated_and_changed_format_snapshots(self) -> None:
        backwards = _bridge()
        backwards.accept_snapshot(_audio(b"\x00\x01\x02\x03"))
        with self.assertRaisesRegex(ValueError, "moved backwards"):
            backwards.accept_snapshot(_audio(b"\x00\x01"))

        mutated = _bridge()
        mutated.accept_snapshot(_audio(b"\x00\x01\x02\x03"))
        with self.assertRaisesRegex(ValueError, "changed prior PCM"):
            mutated.accept_snapshot(_audio(b"\x00\x09\x02\x03\x04\x05"))

        changed_format = _bridge()
        changed_format.accept_snapshot(_audio(b"\x00\x01"))
        with self.assertRaisesRegex(ValueError, "format changed"):
            changed_format.accept_snapshot(
                CapturedAudio(data=b"\x00\x01\x02\x03", sample_rate_hz=48_000)
            )

    def test_rejects_snapshot_between_pcm_samples(self) -> None:
        bridge = _bridge()
        with self.assertRaisesRegex(ValueError, "sample boundary"):
            bridge.accept_snapshot(_audio(b"\x00"))

    def test_release_forgets_turn_and_allows_reuse(self) -> None:
        bridge = _bridge()
        bridge.accept_snapshot(_audio(b"\x00\x01"))

        bridge.release()

        self.assertFalse(bridge.is_active)
        with self.assertRaisesRegex(RuntimeError, "does not own a turn"):
            bridge.accept_snapshot(_audio(b"\x02\x03"))
        bridge.start_turn(session_id="session-2", turn_id="turn-2")
        frames = bridge.accept_snapshot(_audio(b"\x02\x03"))
        self.assertEqual(frames[0].sequence_number, 0)
        self.assertEqual(frames[0].session_id, "session-2")


class RealtimeAudioFrameBridgeTest(unittest.TestCase):
    def test_attaches_ordered_turn_identity_without_retaining_prior_pcm(self) -> None:
        bridge = RealtimeAudioFrameBridge(clock=iter((1.0, 2.0)).__next__)
        bridge.start_turn(session_id="session-1", turn_id="turn-1")

        first = bridge.accept(_audio(b"\x00\x01"))
        second = bridge.accept(_audio(b"\x02\x03"))

        self.assertEqual(first.sequence_number, 0)
        self.assertEqual(first.captured_at_monotonic, 1.0)
        self.assertEqual(first.data, b"\x00\x01")
        self.assertEqual(second.sequence_number, 1)
        self.assertEqual(second.data, b"\x02\x03")
        bridge.release()
        self.assertFalse(bridge.is_active)

    def test_rejects_frames_without_live_turn_ownership(self) -> None:
        bridge = RealtimeAudioFrameBridge()

        with self.assertRaisesRegex(RuntimeError, "does not own"):
            bridge.accept(_audio(b"\x00\x01"))


def _bridge() -> CumulativeAudioFrameBridge:
    bridge = CumulativeAudioFrameBridge()
    bridge.start_turn(session_id="session-1", turn_id="turn-1")
    return bridge


def _audio(data: bytes) -> CapturedAudio:
    return CapturedAudio(
        data=data,
        sample_rate_hz=16_000,
        channels=1,
        sample_width_bytes=2,
    )


if __name__ == "__main__":
    unittest.main()
