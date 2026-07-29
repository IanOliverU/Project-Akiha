"""Voice provider interfaces and shared value objects."""

from project_akiha.providers.voice.base import (
    CapturedAudio,
    MicrophoneCapture,
    MicrophoneCaptureError,
    SpeechSynthesisRequest,
    SynthesizedAudio,
    VoiceInputProvider,
    VoiceOption,
    VoiceOutputProvider,
    VoiceProviderHealth,
    VoiceProviderStatus,
    VoiceTranscript,
)
from project_akiha.providers.voice.qt_microphone import QtMicrophoneCapture

__all__ = [
    "CapturedAudio",
    "MicrophoneCapture",
    "MicrophoneCaptureError",
    "SpeechSynthesisRequest",
    "SynthesizedAudio",
    "VoiceInputProvider",
    "VoiceOption",
    "VoiceOutputProvider",
    "VoiceProviderHealth",
    "VoiceProviderStatus",
    "VoiceTranscript",
    "QtMicrophoneCapture",
]
