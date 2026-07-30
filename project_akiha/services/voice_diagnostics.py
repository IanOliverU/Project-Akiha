"""Provider-neutral health checks for the optional voice stack."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from project_akiha.providers.voice import VoiceProviderHealth
from project_akiha.services.speech_input import SpeechInputService
from project_akiha.services.speech_output import SpeechOutputService


@dataclass(frozen=True, slots=True)
class VoiceDiagnosticsSnapshot:
    """Health results safe to display in Settings."""

    input_health: VoiceProviderHealth
    output_health: VoiceProviderHealth


class VoiceDiagnosticsService:
    """Check STT and TTS providers together without capturing or speaking."""

    def __init__(
        self,
        input_service: SpeechInputService,
        output_service: SpeechOutputService,
    ) -> None:
        self._input_service = input_service
        self._output_service = output_service

    async def check(self) -> VoiceDiagnosticsSnapshot:
        """Return both provider health results."""
        input_health, output_health = await asyncio.gather(
            self._input_service.health(),
            self._output_service.health(),
        )
        return VoiceDiagnosticsSnapshot(
            input_health=input_health,
            output_health=output_health,
        )
