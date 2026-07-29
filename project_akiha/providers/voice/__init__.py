"""Voice provider interfaces and shared value objects."""

from project_akiha.providers.voice.base import (
    CapturedAudio,
    SpeechSynthesisRequest,
    SynthesizedAudio,
    VoiceInputProvider,
    VoiceOption,
    VoiceOutputProvider,
    VoiceProviderHealth,
    VoiceProviderStatus,
    VoiceTranscript,
)

__all__ = [
    "CapturedAudio",
    "SpeechSynthesisRequest",
    "SynthesizedAudio",
    "VoiceInputProvider",
    "VoiceOption",
    "VoiceOutputProvider",
    "VoiceProviderHealth",
    "VoiceProviderStatus",
    "VoiceTranscript",
]
