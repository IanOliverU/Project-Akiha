"""Tests for the lazy faster-whisper provider."""

from __future__ import annotations

import asyncio
import unittest
import wave
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from project_akiha.providers.voice import (
    CapturedAudio,
    VoiceProviderError,
    VoiceProviderStatus,
)
from project_akiha.providers.voice.faster_whisper import FasterWhisperProvider


class FasterWhisperProviderTest(unittest.TestCase):
    """Verify local transcription without importing the optional package."""

    def test_health_reports_available_without_loading_model(self) -> None:
        fixture = _ModelFixture()
        with TemporaryDirectory() as directory:
            provider = _provider(Path(directory), fixture)

            health = asyncio.run(provider.health())

        self.assertEqual(health.status, VoiceProviderStatus.AVAILABLE)
        self.assertEqual(fixture.instances, [])

    def test_health_reports_missing_dependency(self) -> None:
        def missing_loader() -> object:
            raise ImportError("not installed")

        with TemporaryDirectory() as directory:
            provider = FasterWhisperProvider(
                model_size="small",
                language="auto",
                download_root=Path(directory),
                model_class_loader=missing_loader,
            )

            health = asyncio.run(provider.health())

        self.assertEqual(health.status, VoiceProviderStatus.UNAVAILABLE)
        self.assertIn("not installed", health.detail)

    def test_transcribes_in_memory_wav_and_detects_language(self) -> None:
        fixture = _ModelFixture(text=" おはようございます。", language="ja")
        with TemporaryDirectory() as directory:
            model_dir = Path(directory) / "models"
            provider = _provider(model_dir, fixture)

            transcript = asyncio.run(provider.transcribe(_audio()))

        self.assertEqual(transcript.text, "おはようございます。")
        self.assertEqual(transcript.detected_language, "ja")
        self.assertEqual(fixture.wav_format, (1, 2, 16_000))
        self.assertEqual(fixture.model_args["device"], "cpu")
        self.assertEqual(fixture.model_args["compute_type"], "int8")
        self.assertEqual(fixture.model_args["download_root"], str(model_dir))
        self.assertIsNone(fixture.transcribe_args["language"])
        self.assertTrue(fixture.transcribe_args["vad_filter"])
        self.assertIn("Spotify", fixture.transcribe_args["hotwords"])

    def test_reports_bounded_segment_confidence(self) -> None:
        fixture = _ModelFixture(avg_logprob=-0.2, no_speech_prob=0.1)
        with TemporaryDirectory() as directory:
            transcript = asyncio.run(
                _provider(Path(directory), fixture).transcribe(_audio())
            )

        self.assertIsNotNone(transcript.confidence)
        assert transcript.confidence is not None
        self.assertGreater(transcript.confidence, 0.7)
        self.assertLessEqual(transcript.confidence, 1.0)

    def test_clear_short_command_is_not_over_penalized_by_no_speech_score(
        self,
    ) -> None:
        fixture = _ModelFixture(
            text=" Open Spotify.",
            avg_logprob=-0.8,
            no_speech_prob=0.55,
        )
        with TemporaryDirectory() as directory:
            transcript = asyncio.run(
                _provider(Path(directory), fixture).transcribe(_audio())
            )

        self.assertIsNotNone(transcript.confidence)
        assert transcript.confidence is not None
        self.assertGreaterEqual(transcript.confidence, 0.3)

    def test_weak_tokens_and_high_no_speech_remain_low_confidence(self) -> None:
        fixture = _ModelFixture(
            text=" Uncertain words.",
            avg_logprob=-1.8,
            no_speech_prob=0.85,
        )
        with TemporaryDirectory() as directory:
            transcript = asyncio.run(
                _provider(Path(directory), fixture).transcribe(_audio())
            )

        self.assertIsNotNone(transcript.confidence)
        assert transcript.confidence is not None
        self.assertLess(transcript.confidence, 0.3)

    def test_configured_language_is_forwarded(self) -> None:
        fixture = _ModelFixture(text=" Hello.", language="en")
        with TemporaryDirectory() as directory:
            provider = FasterWhisperProvider(
                model_size="small",
                language="en",
                download_root=Path(directory),
                model_class_loader=fixture.load_model_class,
            )

            asyncio.run(provider.transcribe(_audio()))

        self.assertEqual(fixture.transcribe_args["language"], "en")

    def test_model_is_loaded_once(self) -> None:
        fixture = _ModelFixture()
        with TemporaryDirectory() as directory:
            provider = _provider(Path(directory), fixture)

            asyncio.run(provider.transcribe(_audio()))
            asyncio.run(provider.transcribe(_audio()))

        self.assertEqual(len(fixture.instances), 1)

    def test_empty_result_uses_stable_error(self) -> None:
        fixture = _ModelFixture(text="")
        with TemporaryDirectory() as directory:
            provider = _provider(Path(directory), fixture)

            with self.assertRaises(VoiceProviderError) as captured:
                asyncio.run(provider.transcribe(_audio()))

        self.assertEqual(captured.exception.code, "empty_transcript")

    def test_model_load_failure_uses_stable_error(self) -> None:
        def failing_model(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("model unavailable")

        with TemporaryDirectory() as directory:
            provider = FasterWhisperProvider(
                model_size="small",
                language="auto",
                download_root=Path(directory),
                model_class_loader=lambda: failing_model,
            )

            with self.assertRaises(VoiceProviderError) as captured:
                asyncio.run(provider.transcribe(_audio()))

        self.assertEqual(captured.exception.code, "model_load_failed")


class _ModelFixture:
    def __init__(
        self,
        text: str = " Test.",
        language: str = "en",
        avg_logprob: float | None = None,
        no_speech_prob: float | None = None,
    ) -> None:
        self.text = text
        self.language = language
        self.avg_logprob = avg_logprob
        self.no_speech_prob = no_speech_prob
        self.instances: list[object] = []
        self.model_args: dict[str, object] = {}
        self.transcribe_args: dict[str, object] = {}
        self.wav_format: tuple[int, int, int] | None = None

    def load_model_class(self) -> object:
        fixture = self

        class FakeModel:
            def __init__(self, _model_size: str, **kwargs: object) -> None:
                fixture.instances.append(self)
                fixture.model_args = kwargs

            def transcribe(
                self,
                audio: object,
                **kwargs: object,
            ) -> tuple[list[object], object]:
                fixture.transcribe_args = kwargs
                with wave.open(audio, "rb") as wav_file:
                    fixture.wav_format = (
                        wav_file.getnchannels(),
                        wav_file.getsampwidth(),
                        wav_file.getframerate(),
                    )
                return (
                    (
                        [
                            SimpleNamespace(
                                text=fixture.text,
                                avg_logprob=fixture.avg_logprob,
                                no_speech_prob=fixture.no_speech_prob,
                            )
                        ]
                        if fixture.text
                        else []
                    ),
                    SimpleNamespace(language=fixture.language),
                )

        return FakeModel


def _provider(path: Path, fixture: _ModelFixture) -> FasterWhisperProvider:
    return FasterWhisperProvider(
        model_size="small",
        language="auto",
        download_root=path,
        model_class_loader=fixture.load_model_class,
    )


def _audio() -> CapturedAudio:
    return CapturedAudio(
        data=b"\x00\x00\x01\x00",
        sample_rate_hz=16_000,
    )


if __name__ == "__main__":
    unittest.main()
