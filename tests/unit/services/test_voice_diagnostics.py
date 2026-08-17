"""Tests for combined voice provider health checks."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from project_akiha.providers.voice import (
    GptSoVitsProvider,
    GptSoVitsTransportError,
    VoiceProviderHealth,
    VoiceProviderStatus,
)
from project_akiha.services.speech_output import SpeechOutputService
from project_akiha.services.voice_diagnostics import VoiceDiagnosticsService


class VoiceDiagnosticsServiceTest(unittest.TestCase):
    """Verify STT and TTS health remain provider-neutral."""

    def test_returns_both_health_results(self) -> None:
        service = VoiceDiagnosticsService(
            _HealthService(VoiceProviderStatus.AVAILABLE, "STT ready."),
            _HealthService(VoiceProviderStatus.UNAVAILABLE, "TTS unavailable."),
        )

        snapshot = asyncio.run(service.check())

        self.assertEqual(
            snapshot.input_health.status,
            VoiceProviderStatus.AVAILABLE,
        )
        self.assertEqual(
            snapshot.output_health.status,
            VoiceProviderStatus.UNAVAILABLE,
        )

    def test_gpt_sovits_root_404_is_reported_as_available(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "prompt.wav"
            reference.write_bytes(b"reference")
            output = SpeechOutputService(
                GptSoVitsProvider(
                    reference_audio_path=reference,
                    transport=_Root404Transport(),
                )
            )

            snapshot = asyncio.run(
                VoiceDiagnosticsService(
                    _HealthService(VoiceProviderStatus.AVAILABLE, "STT ready."),
                    output,
                ).check()
            )

        self.assertEqual(
            snapshot.output_health.status,
            VoiceProviderStatus.AVAILABLE,
        )


class _Root404Transport:
    def request_bytes(
        self,
        method: str,
        url: str,
        *,
        operation: str,
        payload: object,
        timeout_seconds: float,
    ) -> tuple[bytes, str]:
        del method, url, payload, timeout_seconds
        raise GptSoVitsTransportError(
            "gpt_sovits_http_error",
            f"GPT-SoVITS returned HTTP 404 during {operation}.",
        )


class _HealthService:
    def __init__(self, status: VoiceProviderStatus, detail: str) -> None:
        self._health = VoiceProviderHealth(status, detail)

    async def health(self) -> VoiceProviderHealth:
        return self._health


if __name__ == "__main__":
    unittest.main()
