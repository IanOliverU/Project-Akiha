"""Tests for bounded rolling PCM ownership."""

from __future__ import annotations

import unittest

from project_akiha.core.voice_session import AudioFrame, RollingAudioBuffer


class RollingAudioBufferTest(unittest.TestCase):
    def test_retains_ordered_frames_within_duration_bound(self) -> None:
        buffer = RollingAudioBuffer(maximum_duration_seconds=0.2)
        buffer.start_turn(
            session_id="session-1",
            turn_id="turn-1",
            sample_rate_hz=100,
            channels=1,
            sample_width_bytes=2,
        )

        buffer.accept(_frame(0, b"a" * 20))
        buffer.accept(_frame(1, b"b" * 20))
        buffer.accept(_frame(2, b"c" * 20))

        snapshot = buffer.snapshot()
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.data, b"b" * 20 + b"c" * 20)
        self.assertEqual(snapshot.first_sequence_number, 1)
        self.assertEqual(snapshot.last_sequence_number, 2)
        self.assertAlmostEqual(snapshot.duration_seconds, 0.2)
        self.assertEqual(buffer.retained_bytes, 40)
        self.assertEqual(buffer.evicted_frame_count, 1)

    def test_rejects_wrong_turn_sequence_format_and_timestamp(self) -> None:
        wrong_turn = _buffer()
        with self.assertRaisesRegex(ValueError, "different buffer turn"):
            wrong_turn.accept(_frame(0, turn_id="turn-2"))

        wrong_sequence = _buffer()
        with self.assertRaisesRegex(ValueError, "accepted in sequence"):
            wrong_sequence.accept(_frame(1))

        wrong_format = _buffer()
        with self.assertRaisesRegex(ValueError, "format changed"):
            wrong_format.accept(_frame(0, sample_rate_hz=200))

        backwards_time = _buffer()
        backwards_time.accept(_frame(0, captured_at=2.0))
        with self.assertRaisesRegex(ValueError, "timestamps cannot move backwards"):
            backwards_time.accept(_frame(1, captured_at=1.0))

    def test_rejects_frame_larger_than_entire_buffer(self) -> None:
        buffer = RollingAudioBuffer(maximum_duration_seconds=0.1)
        buffer.start_turn(
            session_id="session-1",
            turn_id="turn-1",
            sample_rate_hz=100,
            channels=1,
            sample_width_bytes=2,
        )

        with self.assertRaisesRegex(ValueError, "duration bound"):
            buffer.accept(_frame(0, b"x" * 22))

    def test_release_discards_audio_and_allows_reuse(self) -> None:
        buffer = _buffer()
        buffer.accept(_frame(0))

        buffer.release()

        self.assertFalse(buffer.is_active)
        self.assertEqual(buffer.retained_bytes, 0)
        self.assertIsNone(buffer.snapshot())
        with self.assertRaisesRegex(RuntimeError, "does not own a turn"):
            buffer.accept(_frame(0))
        buffer.start_turn(
            session_id="session-2",
            turn_id="turn-2",
            sample_rate_hz=100,
            channels=1,
            sample_width_bytes=2,
        )
        buffer.accept(_frame(0, session_id="session-2", turn_id="turn-2"))
        self.assertTrue(buffer.is_active)

    def test_snapshot_repr_does_not_expose_pcm(self) -> None:
        buffer = _buffer()
        buffer.accept(_frame(0, b"secret-pcm"))

        snapshot = buffer.snapshot()

        self.assertIsNotNone(snapshot)
        self.assertNotIn("secret-pcm", repr(snapshot))


def _buffer() -> RollingAudioBuffer:
    buffer = RollingAudioBuffer(maximum_duration_seconds=1.0)
    buffer.start_turn(
        session_id="session-1",
        turn_id="turn-1",
        sample_rate_hz=100,
        channels=1,
        sample_width_bytes=2,
    )
    return buffer


def _frame(
    sequence_number: int,
    data: bytes = b"\x00\x01",
    *,
    session_id: str = "session-1",
    turn_id: str = "turn-1",
    sample_rate_hz: int = 100,
    captured_at: float | None = None,
) -> AudioFrame:
    return AudioFrame(
        session_id=session_id,
        turn_id=turn_id,
        sequence_number=sequence_number,
        captured_at_monotonic=(
            float(sequence_number) if captured_at is None else captured_at
        ),
        sample_rate_hz=sample_rate_hz,
        channels=1,
        sample_width_bytes=2,
        data=data,
    )


if __name__ == "__main__":
    unittest.main()
