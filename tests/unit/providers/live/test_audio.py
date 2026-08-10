"""Tests for bounded Gemini PCM framing and native WAV conversion."""

from __future__ import annotations

import io
import unittest
import wave

from project_akiha.core.voice_session import (
    AudioFrame,
    LiveSessionError,
    LiveSessionErrorCode,
)
from project_akiha.providers.live import (
    GeminiPcmInputChunker,
    NativePcmWaveBuffer,
)


class GeminiPcmInputChunkerTest(unittest.TestCase):
    def test_normalizes_input_to_ordered_40_ms_chunks(self) -> None:
        chunker = GeminiPcmInputChunker(chunk_duration_ms=40)
        chunker.start_turn(session_id="session-1", turn_id="turn-1")

        first = chunker.accept(_frame(data=b"\x01\x00" * 320))
        second = chunker.accept(
            _frame(sequence=1, captured_at=0.02, data=b"\x02\x00" * 640)
        )
        tail = chunker.finish()

        self.assertEqual(first, ())
        self.assertEqual([frame.sequence_number for frame in second], [0])
        self.assertAlmostEqual(second[0].duration_seconds, 0.04)
        self.assertEqual(second[0].data[:2], b"\x01\x00")
        self.assertEqual([frame.sequence_number for frame in tail], [1])
        self.assertAlmostEqual(tail[0].duration_seconds, 0.02)
        self.assertFalse(chunker.is_active)

    def test_pads_only_a_final_tail_shorter_than_20_ms(self) -> None:
        chunker = GeminiPcmInputChunker()
        chunker.start_turn(session_id="session-1", turn_id="turn-1")
        chunker.accept(_frame(data=b"\x01\x00" * 80))

        frames = chunker.finish()

        self.assertEqual(len(frames[0].data), 640)
        self.assertEqual(frames[0].data[:160], b"\x01\x00" * 80)
        self.assertEqual(frames[0].data[160:], b"\x00" * 480)

    def test_rejects_wrong_format_owner_and_sequence(self) -> None:
        chunker = GeminiPcmInputChunker()
        chunker.start_turn(session_id="session-1", turn_id="turn-1")

        with self.assertRaises(LiveSessionError) as wrong_format:
            chunker.accept(_frame(rate=48_000))
        self.assertEqual(
            wrong_format.exception.code,
            LiveSessionErrorCode.UNSUPPORTED_AUDIO_FORMAT,
        )
        with self.assertRaisesRegex(LiveSessionError, "different live turn"):
            chunker.accept(_frame(turn_id="turn-2"))
        with self.assertRaisesRegex(LiveSessionError, "out of order"):
            chunker.accept(_frame(sequence=1))


class NativePcmWaveBufferTest(unittest.TestCase):
    def test_emits_short_24_khz_wave_segments_without_an_audio_owner(self) -> None:
        buffer = NativePcmWaveBuffer(segment_duration_ms=100)
        buffer.start_turn(session_id="session-1", turn_id="turn-1")

        audio = buffer.accept(_frame(rate=24_000, data=b"\x01\x00" * 2_400))

        self.assertEqual(len(audio), 1)
        self.assertEqual(audio[0].sample_rate_hz, 24_000)
        with wave.open(io.BytesIO(audio[0].data), "rb") as reader:
            self.assertEqual(reader.getframerate(), 24_000)
            self.assertEqual(reader.getnchannels(), 1)
            self.assertEqual(reader.getsampwidth(), 2)
            self.assertEqual(reader.getnframes(), 2_400)

    def test_finish_flushes_tail_and_releases_raw_pcm(self) -> None:
        buffer = NativePcmWaveBuffer()
        buffer.start_turn(session_id="session-1", turn_id="turn-1")
        self.assertEqual(
            buffer.accept(_frame(rate=24_000, data=b"\x01\x00" * 480)),
            (),
        )

        audio = buffer.finish()

        self.assertEqual(len(audio), 1)
        self.assertFalse(buffer.is_active)


def _frame(
    *,
    session_id: str = "session-1",
    turn_id: str = "turn-1",
    sequence: int = 0,
    captured_at: float = 0.0,
    rate: int = 16_000,
    data: bytes = b"\x00\x00" * 320,
) -> AudioFrame:
    return AudioFrame(
        session_id=session_id,
        turn_id=turn_id,
        sequence_number=sequence,
        captured_at_monotonic=captured_at,
        sample_rate_hz=rate,
        channels=1,
        sample_width_bytes=2,
        data=data,
    )


if __name__ == "__main__":
    unittest.main()
