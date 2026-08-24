"""Tests for the GPT-SoVITS local HTTP provider."""

from __future__ import annotations

import asyncio
import io
import tempfile
import unittest
import wave
from pathlib import Path
from typing import Any

from project_akiha.providers.voice import (
    GptSoVitsProvider,
    GptSoVitsTransportError,
    SpeechSynthesisRequest,
    VoiceProviderError,
    VoiceProviderStatus,
)


class GptSoVitsProviderTest(unittest.TestCase):
    def test_health_requires_reference_audio(self) -> None:
        provider = GptSoVitsProvider(transport=_Transport())

        health = asyncio.run(provider.health())

        self.assertEqual(health.status, VoiceProviderStatus.UNAVAILABLE)
        self.assertIn("reference prompt audio", health.detail)

    def test_health_accepts_official_api_root_404(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "prompt.wav"
            reference.write_bytes(b"reference")
            provider = GptSoVitsProvider(
                reference_audio_path=reference,
                transport=_Transport(
                    error=GptSoVitsTransportError(
                        "gpt_sovits_http_error",
                        "GPT-SoVITS returned HTTP 404 during health check.",
                    ),
                ),
            )

            health = asyncio.run(provider.health())

        self.assertEqual(health.status, VoiceProviderStatus.AVAILABLE)

    def test_synthesize_posts_reference_prompt_and_returns_wav(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "prompt.wav"
            reference.write_bytes(b"reference")
            transport = _Transport(audio=(_wav_bytes(24_000), "audio/wav"))
            provider = GptSoVitsProvider(
                api_url="http://localhost:9880/",
                reference_audio_path=reference,
                prompt_text="覚悟はよくて?",
                transport=transport,
            )

            audio = asyncio.run(
                provider.synthesize(
                    SpeechSynthesisRequest(
                        text="こんにちは。",
                        voice_id="akiha",
                        speaking_rate=1.1,
                    )
                )
            )

        self.assertEqual(audio.data, _wav_bytes(24_000))
        self.assertEqual(audio.sample_rate_hz, 24_000)
        self.assertEqual(transport.calls[0]["url"], "http://localhost:9880/tts")
        self.assertEqual(transport.calls[0]["payload"]["text_lang"], "ja")
        self.assertEqual(transport.calls[0]["payload"]["prompt_lang"], "ja")
        self.assertEqual(transport.calls[0]["payload"]["speed_factor"], 1.1)
        self.assertEqual(
            transport.calls[0]["payload"]["ref_audio_path"], str(reference)
        )

    def test_synthesize_rejects_error_json_without_echoing_spoken_text(self) -> None:
        secret = "private spoken response"
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "prompt.wav"
            reference.write_bytes(b"reference")
            provider = GptSoVitsProvider(
                reference_audio_path=reference,
                transport=_Transport(
                    audio=(
                        b'{"detail":"model failed"}',
                        "application/json",
                    )
                ),
            )

            with self.assertRaises(VoiceProviderError) as captured:
                asyncio.run(provider.synthesize(SpeechSynthesisRequest(text=secret)))

        self.assertEqual(captured.exception.code, "gpt_sovits_error_response")
        self.assertNotIn(secret, str(captured.exception))

    def test_synthesize_collapses_paragraph_whitespace_for_speech_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "prompt.wav"
            reference.write_bytes(b"reference")
            transport = _Transport(audio=(_wav_bytes(24_000), "audio/wav"))
            provider = GptSoVitsProvider(
                reference_audio_path=reference,
                transport=transport,
            )

            asyncio.run(
                provider.synthesize(
                    SpeechSynthesisRequest(text="First sentence.\n\nSecond sentence.")
                )
            )

        self.assertEqual(
            transport.calls[0]["payload"]["text"],
            "First sentence. Second sentence.",
        )

    def test_synthesize_rejects_invalid_voice_id_before_http(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "prompt.wav"
            reference.write_bytes(b"reference")
            transport = _Transport()
            provider = GptSoVitsProvider(
                reference_audio_path=reference,
                transport=transport,
            )

            with self.assertRaises(VoiceProviderError) as captured:
                asyncio.run(
                    provider.synthesize(
                        SpeechSynthesisRequest(text="Test.", voice_id="other")
                    )
                )

        self.assertEqual(captured.exception.code, "invalid_voice_id")
        self.assertEqual(transport.calls, [])


class _Transport:
    def __init__(
        self,
        *,
        audio: tuple[bytes, str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.audio = audio or (b"{}", "application/json")
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def request_bytes(
        self,
        method: str,
        url: str,
        *,
        operation: str,
        payload: dict[str, Any] | None,
        timeout_seconds: float,
    ) -> tuple[bytes, str]:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "operation": operation,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.error is not None:
            raise self.error
        return self.audio


def _wav_bytes(sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * 8)
    return buffer.getvalue()
