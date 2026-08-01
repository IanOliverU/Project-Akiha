"""Tests for the non-owning Qt snapshot-to-frame bridge prototype."""

from __future__ import annotations

import unittest

from project_akiha.providers.voice import CapturedAudio
from spikes.voice_pipeline.qt_audio_bridge import QtSnapshotAudioFrameBridge


class QtSnapshotAudioFrameBridgeTest(unittest.TestCase):
    def test_emits_only_pcm_appended_to_cumulative_snapshots(self) -> None:
        bridge = QtSnapshotAudioFrameBridge(
            maximum_frame_duration_ms=1,
            clock_ns=iter((10, 20, 30)).__next__,
        )
        bridge.start(session_id="session-1", turn_id=7)

        first = bridge.accept_snapshot(_audio(b"\x00\x01\x02\x03"))
        second = bridge.accept_snapshot(_audio(b"\x00\x01\x02\x03\x04\x05"))

        self.assertEqual([frame.data for frame in first], [b"\x00\x01\x02\x03"])
        self.assertEqual([frame.data for frame in second], [b"\x04\x05"])
        self.assertEqual([frame.sequence for frame in (*first, *second)], [1, 2])
        self.assertTrue(all(frame.turn_id == 7 for frame in (*first, *second)))

    def test_splits_large_snapshot_on_pcm_sample_boundaries(self) -> None:
        bridge = QtSnapshotAudioFrameBridge(maximum_frame_duration_ms=100)
        bridge.start(session_id="session-1", turn_id=1)

        frames = bridge.accept_snapshot(_audio(bytes(8_000)))

        self.assertEqual([len(frame.data) for frame in frames], [3_200, 3_200, 1_600])
        self.assertAlmostEqual(frames[0].duration_seconds, 0.1)
        self.assertAlmostEqual(frames[-1].duration_seconds, 0.05)

    def test_duplicate_snapshot_emits_no_duplicate_frames(self) -> None:
        bridge = QtSnapshotAudioFrameBridge()
        bridge.start(session_id="session-1", turn_id=1)
        audio = _audio(b"\x00\x01")

        bridge.accept_snapshot(audio)

        self.assertEqual(bridge.accept_snapshot(audio), ())

    def test_rejects_snapshot_that_mutates_prior_pcm(self) -> None:
        bridge = QtSnapshotAudioFrameBridge()
        bridge.start(session_id="session-1", turn_id=1)
        bridge.accept_snapshot(_audio(b"\x00\x01\x02\x03"))

        with self.assertRaisesRegex(ValueError, "changed previously emitted"):
            bridge.accept_snapshot(_audio(b"\x00\x09\x02\x03\x04\x05"))

    def test_rejects_backwards_snapshot_and_mid_turn_format_change(self) -> None:
        backwards = QtSnapshotAudioFrameBridge()
        backwards.start(session_id="session-1", turn_id=1)
        backwards.accept_snapshot(_audio(b"\x00\x01\x02\x03"))

        with self.assertRaisesRegex(ValueError, "moved backwards"):
            backwards.accept_snapshot(_audio(b"\x00\x01"))

        changed = QtSnapshotAudioFrameBridge()
        changed.start(session_id="session-1", turn_id=1)
        changed.accept_snapshot(_audio(b"\x00\x01"))
        with self.assertRaisesRegex(ValueError, "format changed"):
            changed.accept_snapshot(
                CapturedAudio(
                    data=b"\x00\x01\x02\x03",
                    sample_rate_hz=48_000,
                )
            )

    def test_stop_releases_snapshot_without_stopping_qt_capture(self) -> None:
        bridge = QtSnapshotAudioFrameBridge()
        bridge.start(session_id="session-1", turn_id=1)
        bridge.accept_snapshot(_audio(b"\x00\x01"))

        bridge.stop()

        self.assertFalse(bridge.is_active)
        with self.assertRaisesRegex(RuntimeError, "not active"):
            bridge.accept_snapshot(_audio(b"\x02\x03"))


def _audio(data: bytes) -> CapturedAudio:
    return CapturedAudio(
        data=data,
        sample_rate_hz=16_000,
        channels=1,
        sample_width_bytes=2,
    )


if __name__ == "__main__":
    unittest.main()
