"""Tests for the reproducible V2 recognition benchmark."""

from __future__ import annotations

import unittest

from scripts.benchmark_voice_recognition import benchmark, render_markdown


class VoiceRecognitionBenchmarkTest(unittest.IsolatedAsyncioTestCase):
    async def test_rolling_bounds_long_partial_work(self) -> None:
        comparisons = await benchmark((3.0, 30.0), repeats=1)
        short, long = comparisons

        self.assertEqual(short.legacy.first_partial_audio_seconds, 0.6)
        self.assertEqual(short.rolling.first_partial_audio_seconds, 0.6)
        self.assertEqual(short.legacy.final_audio_seconds, 3.0)
        self.assertEqual(short.rolling.final_audio_seconds, 3.0)
        self.assertEqual(long.legacy.final_audio_seconds, 30.0)
        self.assertEqual(long.rolling.final_audio_seconds, 30.0)
        self.assertEqual(long.rolling.maximum_partial_audio_seconds, 8.0)
        self.assertGreater(long.processed_audio_reduction_percent, 50.0)

    async def test_markdown_reports_both_strategies(self) -> None:
        rendered = render_markdown(await benchmark((10.0,), repeats=1))

        self.assertIn("cumulative", rendered)
        self.assertIn("rolling", rendered)
        self.assertIn("rolling reduction", rendered)


if __name__ == "__main__":
    unittest.main()
