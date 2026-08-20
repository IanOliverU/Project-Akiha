"""Tests for voice provider composition at application startup."""

from __future__ import annotations

import asyncio
import io
import unittest
import wave
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from project_akiha.app.main import (
    _build_speech_output_service,
    _provider_runtime_smoke_request,
)
from project_akiha.config import VoiceConfig
from project_akiha.providers.voice import VoiceProviderHealth, VoiceProviderStatus
from project_akiha.services.gpt_sovits_reference import resolve_gpt_sovits_prompt


class MainVoiceServicesTest(unittest.TestCase):
    """Verify saved settings select the intended output provider."""

    def test_akiha_settings_select_gpt_sovits_provider(self) -> None:
        provider = _AvailableProvider()

        with patch(
            "project_akiha.app.main.GptSoVitsProvider",
            return_value=provider,
        ) as provider_factory:
            service = _build_speech_output_service(
                VoiceConfig(output_provider="gpt-sovits")
            )

        provider_factory.assert_called_once()
        self.assertEqual(
            asyncio.run(service.health()).status,
            VoiceProviderStatus.AVAILABLE,
        )

    def test_disabled_output_uses_unavailable_provider(self) -> None:
        service = _build_speech_output_service(VoiceConfig(output_provider="disabled"))

        health = asyncio.run(service.health())

        self.assertEqual(health.status, VoiceProviderStatus.UNAVAILABLE)
        self.assertIn("disabled", health.detail)

    def test_runtime_smoke_arguments_are_explicit(self) -> None:
        request = _provider_runtime_smoke_request(
            [
                "--provider-runtime-smoke-report=C:/temp/report.json",
                "--skip-gemini-network",
            ]
        )

        self.assertEqual(request, (Path("C:/temp/report.json"), False))
        self.assertIsNone(_provider_runtime_smoke_request([]))

    def test_packaged_layout_finds_external_private_reference_directory(self) -> None:
        with TemporaryDirectory() as directory:
            project_root = Path(directory) / "Project Akiha"
            packaged_root = project_root / "dist" / "nuitka-development" / "main.dist"
            reference_dir = project_root / "AKIHA VOICE"
            packaged_root.mkdir(parents=True)
            reference_dir.mkdir()
            reference = reference_dir / "reference.wav"
            reference.write_bytes(_wav_bytes(duration_seconds=4.0))

            resolved, prompt = resolve_gpt_sovits_prompt(
                packaged_root,
                "AKIHA VOICE",
                "",
            )

        self.assertEqual(resolved, reference.resolve())
        self.assertEqual(prompt, "")


class _AvailableProvider:
    async def health(self) -> VoiceProviderHealth:
        return VoiceProviderHealth(VoiceProviderStatus.AVAILABLE)


def _wav_bytes(*, duration_seconds: float) -> bytes:
    sample_rate = 8_000
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * int(sample_rate * duration_seconds))
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
