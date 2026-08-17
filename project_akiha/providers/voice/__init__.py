"""Voice provider interfaces and shared value objects."""

from project_akiha.providers.voice.base import (
    AudioPlayback,
    AudioPlaybackError,
    CapturedAudio,
    MicrophoneActivity,
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
from project_akiha.providers.voice.gpt_sovits import (
    GptSoVitsProvider,
    GptSoVitsTransport,
    GptSoVitsTransportError,
    UrllibGptSoVitsTransport,
)
from project_akiha.providers.voice.qt_microphone import QtMicrophoneCapture
from project_akiha.providers.voice.qt_playback import QtAudioPlayback
from project_akiha.providers.voice.unavailable import UnavailableVoiceOutputProvider

__all__ = [
    "AudioPlayback",
    "AudioPlaybackError",
    "CapturedAudio",
    "MicrophoneActivity",
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
    "QtAudioPlayback",
    "FasterWhisperProvider",
    "GptSoVitsProvider",
    "GptSoVitsTransport",
    "GptSoVitsTransportError",
    "UrllibGptSoVitsTransport",
    "UnavailableVoiceOutputProvider",
]
