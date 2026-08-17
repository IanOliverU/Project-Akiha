"""Tests for the read-only GPT-SoVITS dataset preparation boundary."""

from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path

from project_akiha.services.gpt_sovits_dataset import GptSovitsDatasetBuilder


class GptSovitsDatasetBuilderTest(unittest.TestCase):
    def test_builds_derived_audio_and_keeps_source_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference_dir = root / "AKIHA VOICE"
            output_dir = root / "dataset"
            reference_dir.mkdir()
            source = reference_dir / "Akiha_test.wav"
            original = _write_test_wav(source)

            manifest = GptSovitsDatasetBuilder(
                reference_dir,
                output_dir,
            ).build({"Akiha_test.wav": "これはテストです。"})

            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(len(manifest.entries), 1)
            self.assertTrue(manifest.entries[0].audio.endswith(".wav"))
            self.assertIn(
                "|akiha|ja|これはテストです。",
                manifest.list_path.read_text(encoding="utf-8"),
            )
            with wave.open(manifest.entries[0].audio, "rb") as derived:
                self.assertEqual(derived.getframerate(), 32_000)
                self.assertEqual(derived.getnchannels(), 1)
                self.assertEqual(derived.getsampwidth(), 2)


def _write_test_wav(path: Path) -> bytes:
    import math
    import struct

    samples = [
        int(
            (0.05 if (index // 441) % 5 == 0 else 0.3)
            * 32767
            * math.sin(2 * math.pi * 220 * index / 22_050)
        )
        for index in range(22_050)
    ]
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(22_050)
        output.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))
    return path.read_bytes()


if __name__ == "__main__":
    unittest.main()
