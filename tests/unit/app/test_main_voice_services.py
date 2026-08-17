"""Tests for voice provider composition at application startup."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from project_akiha.app.main import _build_speech_output_service
from project_akiha.config import VoiceConfig
from project_akiha.providers.voice import VoiceProviderHealth, VoiceProviderStatus


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

    def test_voicevox_settings_are_passed_to_provider(self) -> None:
        provider = _AvailableProvider()

        with patch(
            "project_akiha.app.main.VoiceVoxProvider",
            return_value=provider,
        ) as provider_factory:
            service = _build_speech_output_service(
                VoiceConfig(
                    output_provider="voicevox",
                    output_base_url="http://localhost:50100",
                    request_timeout_seconds=17,
                )
            )

        provider_factory.assert_called_once_with(
            base_url="http://localhost:50100",
            timeout_seconds=17.0,
        )
        self.assertEqual(
            asyncio.run(service.health()).status,
            VoiceProviderStatus.AVAILABLE,
        )

    def test_disabled_output_uses_unavailable_provider(self) -> None:
        service = _build_speech_output_service(VoiceConfig(output_provider="disabled"))

        health = asyncio.run(service.health())

        self.assertEqual(health.status, VoiceProviderStatus.UNAVAILABLE)
        self.assertIn("disabled", health.detail)


class _AvailableProvider:
    async def health(self) -> VoiceProviderHealth:
        return VoiceProviderHealth(VoiceProviderStatus.AVAILABLE)


if __name__ == "__main__":
    unittest.main()
