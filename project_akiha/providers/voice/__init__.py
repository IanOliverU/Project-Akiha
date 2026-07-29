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
    VoiceProviderError,
    VoiceProviderHealth,
    VoiceProviderStatus,
    VoiceTranscript,
)
from project_akiha.providers.voice.faster_whisper import FasterWhisperProvider
from project_akiha.providers.voice.qt_microphone import QtMicrophoneCapture
from project_akiha.providers.voice.unavailable import UnavailableVoiceOutputProvider
from project_akiha.providers.voice.voicevox import (
    UrllibVoiceVoxTransport,
    VoiceVoxProvider,
    VoiceVoxTransport,
    VoiceVoxTransportError,
)

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
    "VoiceProviderError",
    "VoiceProviderStatus",
    "VoiceTranscript",
    "QtMicrophoneCapture",
    "FasterWhisperProvider",
    "UnavailableVoiceOutputProvider",
    "UrllibVoiceVoxTransport",
    "VoiceVoxProvider",
    "VoiceVoxTransport",
    "VoiceVoxTransportError",
]
