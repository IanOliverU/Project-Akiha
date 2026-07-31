"""Framework-free contracts shared by local voice providers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class VoiceProviderStatus(StrEnum):
    """Operational states reported by a voice provider."""

    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"
    AVAILABLE = "available"


@dataclass(frozen=True, slots=True)
class VoiceProviderHealth:
    """A provider health result suitable for settings diagnostics."""

    status: VoiceProviderStatus
    detail: str = ""


@dataclass(frozen=True, slots=True)
class CapturedAudio:
    """Provider-neutral PCM audio captured by push-to-talk."""

    data: bytes
    sample_rate_hz: int
    channels: int = 1
    sample_width_bytes: int = 2
    language: str | None = None

    def __post_init__(self) -> None:
        if not self.data:
            raise ValueError("Captured audio data cannot be empty.")
        if self.sample_rate_hz <= 0:
            raise ValueError("Audio sample rate must be greater than zero.")
        if self.channels <= 0:
            raise ValueError("Audio channel count must be greater than zero.")
        if self.sample_width_bytes <= 0:
            raise ValueError("Audio sample width must be greater than zero.")


@dataclass(frozen=True, slots=True)
class VoiceTranscript:
    """Text recognized from a captured audio request."""

    text: str
    detected_language: str | None = None
    confidence: float | None = None

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("Voice transcript text cannot be empty.")
        if self.confidence is not None and (
            isinstance(self.confidence, bool) or not 0.0 <= self.confidence <= 1.0
        ):
            raise ValueError(
                "Voice transcript confidence must be between zero and one."
            )


@dataclass(frozen=True, slots=True)
class MicrophoneActivity:
    """Coarse microphone state safe to display without exposing audio."""

    activity: str
    level: str
    silence_remaining_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.activity not in {"calibrating", "waiting", "speaking", "pause"}:
            raise ValueError("Unknown microphone activity state.")
        if self.level not in {"quiet", "ambient", "speech", "loud"}:
            raise ValueError("Unknown microphone level band.")
        if (
            self.silence_remaining_seconds is not None
            and self.silence_remaining_seconds < 0
        ):
            raise ValueError("Silence countdown cannot be negative.")


@dataclass(frozen=True, slots=True)
class SpeechSynthesisRequest:
    """Provider-neutral text-to-speech request."""

    text: str
    voice_id: str | None = None
    language: str = "ja-JP"
    speaking_rate: float = 1.0

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("Speech synthesis text cannot be empty.")
        if not self.language.strip():
            raise ValueError("Speech synthesis language cannot be empty.")
        if not 0.5 <= self.speaking_rate <= 2.0:
            raise ValueError("Speech synthesis rate must be between 0.5 and 2.0.")


@dataclass(frozen=True, slots=True)
class SynthesizedAudio:
    """Encoded audio returned by a text-to-speech provider."""

    data: bytes
    media_type: str = "audio/wav"
    sample_rate_hz: int | None = None

    def __post_init__(self) -> None:
        if not self.data:
            raise ValueError("Synthesized audio data cannot be empty.")
        if not self.media_type.strip():
            raise ValueError("Synthesized audio media type cannot be empty.")
        if self.sample_rate_hz is not None and self.sample_rate_hz <= 0:
            raise ValueError("Synthesized audio sample rate must be positive.")


@dataclass(frozen=True, slots=True)
class VoiceOption:
    """A selectable voice exposed by a speech synthesis provider."""

    identifier: str
    name: str
    language: str | None = None

    def __post_init__(self) -> None:
        if not self.identifier.strip():
            raise ValueError("Voice option identifier cannot be empty.")
        if not self.name.strip():
            raise ValueError("Voice option name cannot be empty.")


class MicrophoneCaptureError(RuntimeError):
    """A privacy-safe microphone capture failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code.strip() or "microphone_error"


class VoiceProviderError(RuntimeError):
    """A provider failure with a stable diagnostic code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code.strip() or "voice_provider_error"


class AudioPlaybackError(RuntimeError):
    """A privacy-safe audio playback failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code.strip() or "audio_playback_error"


class MicrophoneCapture(Protocol):
    """Capture PCM audio only while push-to-talk is active."""

    @property
    def is_capturing(self) -> bool:
        """Return whether microphone capture is currently active."""

    def set_device_name(self, device_name: str) -> None:
        """Select an input device for the next capture."""

    def start(
        self,
        *,
        timeout_seconds: int,
        on_timeout: Callable[[], None],
        on_error: Callable[[str, str], None],
        on_audio_snapshot: Callable[[CapturedAudio], None] | None = None,
        on_silence: Callable[[], None] | None = None,
        on_activity: Callable[[MicrophoneActivity], None] | None = None,
        live_interval_seconds: float = 1.0,
        silence_timeout_seconds: float = 1.2,
        auto_stop_on_silence: bool = False,
    ) -> None:
        """Start temporary microphone capture."""

    def stop(self) -> CapturedAudio:
        """Stop capture and return the temporary PCM audio."""

    def cancel(self) -> None:
        """Discard any temporary captured audio."""


class VoiceInputProvider(Protocol):
    """Transcribe captured audio without owning microphone capture."""

    async def transcribe(self, audio: CapturedAudio) -> VoiceTranscript:
        """Return recognized text for captured audio."""

    async def health(self) -> VoiceProviderHealth:
        """Return whether the provider is ready for transcription."""


class VoiceOutputProvider(Protocol):
    """Synthesize speech without owning audio playback."""

    async def synthesize(
        self,
        request: SpeechSynthesisRequest,
    ) -> SynthesizedAudio:
        """Return encoded audio for the requested spoken text."""

    async def available_voices(self) -> Sequence[VoiceOption]:
        """Return selectable voices exposed by the provider."""

    async def health(self) -> VoiceProviderHealth:
        """Return whether the provider is ready for synthesis."""


class AudioPlayback(Protocol):
    """Play temporary synthesized audio without owning voice state."""

    @property
    def is_active(self) -> bool:
        """Return whether audio is loading or playing."""

    def apply_settings(self, device_name: str, volume_percent: int) -> None:
        """Apply output settings, stopping active playback if necessary."""

    def play(
        self,
        audio: SynthesizedAudio,
        *,
        on_started: Callable[[], None],
        on_finished: Callable[[], None],
        on_error: Callable[[str, str], None],
    ) -> None:
        """Start temporary audio playback."""

    def stop(self) -> None:
        """Stop playback and release temporary audio."""
