"""Tests for combined voice provider health checks."""

from __future__ import annotations

import asyncio
import unittest

from project_akiha.providers.voice import (
    VoiceProviderHealth,
    VoiceProviderStatus,
)
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


class _HealthService:
    def __init__(self, status: VoiceProviderStatus, detail: str) -> None:
        self._health = VoiceProviderHealth(status, detail)

    async def health(self) -> VoiceProviderHealth:
        return self._health


if __name__ == "__main__":
    unittest.main()
