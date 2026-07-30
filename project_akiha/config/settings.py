"""Typed TOML configuration for Project Akiha."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

HOSTED_AI_PROVIDERS = frozenset(
    {
        "gemini",
        "openai",
        "openrouter",
        "kimi",
        "grok",
        "openai-compatible",
    }
)
AI_PROVIDERS = frozenset({"mock", "ollama", *HOSTED_AI_PROVIDERS})


@dataclass(frozen=True, slots=True)
class PetWindowConfig:
    """Settings that control the Phase 1 desktop pet window."""

    width: int = 180
    height: int = 220
    frames_per_second: int = 24
    start_x: int = 120
    start_y: int = 120
    always_on_top: bool = True
    animation_manifest_path: str = "assets/animations/manifest.toml"
    walking_speed_pixels: int = 2

    def __post_init__(self) -> None:
        """Validate values that would make the UI unusable."""
        if self.width <= 0:
            raise ValueError("pet_window.width must be greater than zero.")
        if self.height <= 0:
            raise ValueError("pet_window.height must be greater than zero.")
        if self.frames_per_second <= 0:
            raise ValueError("pet_window.frames_per_second must be greater than zero.")
        if self.walking_speed_pixels <= 0:
            message = "pet_window.walking_speed_pixels must be greater than zero."
            raise ValueError(message)


@dataclass(frozen=True, slots=True)
class AIConfig:
    """Settings for companion chat provider selection."""

    provider: str = "mock"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    hosted_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    hosted_model: str = "gemini-3.6-flash"
    request_timeout_seconds: int = 60

    def __post_init__(self) -> None:
        """Validate AI provider settings."""
        if self.provider not in AI_PROVIDERS:
            supported = ", ".join(sorted(AI_PROVIDERS))
            raise ValueError(f"ai.provider must be one of: {supported}.")
        if not self.ollama_base_url.strip():
            raise ValueError("ai.ollama_base_url cannot be empty.")
        _validate_http_url(self.ollama_base_url, "ai.ollama_base_url")
        if not self.ollama_model.strip():
            raise ValueError("ai.ollama_model cannot be empty.")
        if not self.hosted_base_url.strip():
            raise ValueError("ai.hosted_base_url cannot be empty.")
        _validate_http_url(self.hosted_base_url, "ai.hosted_base_url")
        if not self.hosted_model.strip():
            raise ValueError("ai.hosted_model cannot be empty.")
        if self.request_timeout_seconds <= 0:
            raise ValueError("ai.request_timeout_seconds must be greater than zero.")

    @property
    def uses_hosted_api(self) -> bool:
        """Return whether the selected provider uses Chat Completions."""
        return self.provider in HOSTED_AI_PROVIDERS

    @property
    def requires_api_key(self) -> bool:
        """Return whether the selected preset requires a hosted API key."""
        return self.provider in HOSTED_AI_PROVIDERS - {"openai-compatible"}


@dataclass(frozen=True, slots=True)
class PersonalityConfig:
    """Settings that shape Akiha's chat persona."""

    character_name: str = "Akiha"
    system_prompt: str = (
        "You are {character_name}, a warm, concise desktop companion. "
        "Be helpful, friendly, and direct. Keep replies grounded in what the "
        "user asked for, and do not claim abilities the app has not built yet."
    )

    def __post_init__(self) -> None:
        """Validate personality settings."""
        if not self.character_name.strip():
            raise ValueError("personality.character_name cannot be empty.")
        if not self.system_prompt.strip():
            raise ValueError("personality.system_prompt cannot be empty.")

    def rendered_system_prompt(self) -> str:
        """Return the prompt text sent to the active AI provider."""
        return self.system_prompt.replace(
            "{character_name}",
            self.character_name.strip(),
        )


@dataclass(frozen=True, slots=True)
class MemoryConfig:
    """Settings for the Phase 3 memory pipeline."""

    enabled: bool = True
    retrieval_limit: int = 5
    require_approval: bool = False

    def __post_init__(self) -> None:
        """Validate memory settings."""
        if self.retrieval_limit <= 0:
            raise ValueError("memory.retrieval_limit must be greater than zero.")


def _validate_hh_mm(value: str, field_name: str) -> None:
    parts = value.split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError(f"{field_name} must use HH:MM format.")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour > 23 or minute > 59:
        raise ValueError(f"{field_name} must use HH:MM format.")


def _validate_http_url(value: str, field_name: str) -> None:
    parsed_url = urlparse(value)
    if parsed_url.scheme not in {"http", "https"}:
        raise ValueError(f"{field_name} must use http or https.")
    if not parsed_url.netloc:
        raise ValueError(f"{field_name} must include a host.")


@dataclass(frozen=True, slots=True)
class BehaviorConfig:
    """Settings for Phase 4 activity awareness and proactive behavior."""

    enabled: bool = True
    proactive_enabled: bool = False
    idle_after_seconds: int = 300
    away_after_seconds: int = 900
    minimum_seconds_between_notifications: int = 1800
    allow_notifications_while_away: bool = False
    scheduled_check_ins_enabled: bool = False
    scheduled_check_in_interval_seconds: int = 3600
    quiet_hours_enabled: bool = False
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "07:00"

    def __post_init__(self) -> None:
        """Validate behavior settings."""
        if self.idle_after_seconds <= 0:
            raise ValueError("behavior.idle_after_seconds must be greater than zero.")
        if self.away_after_seconds <= self.idle_after_seconds:
            message = (
                "behavior.away_after_seconds must be greater than idle_after_seconds."
            )
            raise ValueError(message)
        if self.minimum_seconds_between_notifications <= 0:
            message = (
                "behavior.minimum_seconds_between_notifications must be greater "
                "than zero."
            )
            raise ValueError(message)
        if self.scheduled_check_in_interval_seconds <= 0:
            message = (
                "behavior.scheduled_check_in_interval_seconds must be greater "
                "than zero."
            )
            raise ValueError(message)
        _validate_hh_mm(self.quiet_hours_start, "behavior.quiet_hours_start")
        _validate_hh_mm(self.quiet_hours_end, "behavior.quiet_hours_end")


@dataclass(frozen=True, slots=True)
class VoiceConfig:
    """Settings for optional Phase 7 local voice providers."""

    enabled: bool = False
    push_to_talk_enabled: bool = True
    input_provider: str = "faster-whisper"
    input_model: str = "small"
    input_language: str = "auto"
    input_device: str = ""
    output_provider: str = "voicevox"
    output_base_url: str = "http://127.0.0.1:50021"
    output_voice_id: str = "0"
    output_device: str = ""
    automatic_speech_enabled: bool = False
    proactive_speech_enabled: bool = False
    english_subtitles_enabled: bool = False
    live_transcription_enabled: bool = False
    auto_stop_on_silence_enabled: bool = False
    auto_send_transcript_enabled: bool = False
    silence_timeout_seconds: float = 1.2
    volume_percent: int = 100
    speaking_rate: float = 1.0
    capture_timeout_seconds: int = 30
    request_timeout_seconds: int = 30

    def __post_init__(self) -> None:
        """Validate provider-neutral voice settings."""
        if self.input_provider not in {"disabled", "faster-whisper"}:
            message = (
                "voice.input_provider must be either 'disabled' or " "'faster-whisper'."
            )
            raise ValueError(message)
        if self.output_provider not in {"disabled", "voicevox"}:
            message = "voice.output_provider must be either 'disabled' or 'voicevox'."
            raise ValueError(message)
        if not self.input_model.strip():
            raise ValueError("voice.input_model cannot be empty.")
        if not self.input_language.strip():
            raise ValueError("voice.input_language cannot be empty.")
        if not self.output_voice_id.strip():
            raise ValueError("voice.output_voice_id cannot be empty.")

        parsed_output_url = urlparse(self.output_base_url)
        if parsed_output_url.scheme not in {"http", "https"}:
            raise ValueError("voice.output_base_url must use http or https.")
        if not parsed_output_url.netloc:
            raise ValueError("voice.output_base_url must include a host.")
        if not 0 <= self.volume_percent <= 100:
            raise ValueError("voice.volume_percent must be between 0 and 100.")
        if not 0.5 <= self.speaking_rate <= 2.0:
            raise ValueError("voice.speaking_rate must be between 0.5 and 2.0.")
        if not 0.5 <= self.silence_timeout_seconds <= 5.0:
            raise ValueError(
                "voice.silence_timeout_seconds must be between 0.5 and 5.0."
            )
        if self.capture_timeout_seconds <= 0:
            raise ValueError("voice.capture_timeout_seconds must be greater than zero.")
        if self.request_timeout_seconds <= 0:
            raise ValueError("voice.request_timeout_seconds must be greater than zero.")

    @property
    def input_enabled(self) -> bool:
        """Return whether speech input may be used."""
        return self.enabled and self.input_provider != "disabled"

    @property
    def output_enabled(self) -> bool:
        """Return whether speech output may be used."""
        return self.enabled and self.output_provider != "disabled"


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Full application configuration."""

    pet_window: PetWindowConfig = PetWindowConfig()
    ai: AIConfig = AIConfig()
    personality: PersonalityConfig = PersonalityConfig()
    memory: MemoryConfig = MemoryConfig()
    behavior: BehaviorConfig = BehaviorConfig()
    voice: VoiceConfig = VoiceConfig()

    def with_pet_window(self, pet_window: PetWindowConfig) -> AppConfig:
        """Return a copy with updated pet window settings."""
        return replace(self, pet_window=pet_window)

    def with_ai(self, ai: AIConfig) -> AppConfig:
        """Return a copy with updated AI settings."""
        return replace(self, ai=ai)

    def with_personality(self, personality: PersonalityConfig) -> AppConfig:
        """Return a copy with updated personality settings."""
        return replace(self, personality=personality)

    def with_memory(self, memory: MemoryConfig) -> AppConfig:
        """Return a copy with updated memory settings."""
        return replace(self, memory=memory)

    def with_behavior(self, behavior: BehaviorConfig) -> AppConfig:
        """Return a copy with updated behavior settings."""
        return replace(self, behavior=behavior)

    def with_voice(self, voice: VoiceConfig) -> AppConfig:
        """Return a copy with updated voice settings."""
        return replace(self, voice=voice)


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load default config and optionally overlay user-provided TOML values."""
    default_path = Path(__file__).with_name("default.toml")
    data = _read_toml(default_path)

    if config_path is not None:
        data = _deep_merge(data, _read_toml(config_path))

    pet_window_data = data.get("pet_window", {})
    if not isinstance(pet_window_data, dict):
        raise ValueError("pet_window config must be a TOML table.")

    ai_data = data.get("ai", {})
    if not isinstance(ai_data, dict):
        raise ValueError("ai config must be a TOML table.")

    personality_data = data.get("personality", {})
    if not isinstance(personality_data, dict):
        raise ValueError("personality config must be a TOML table.")

    memory_data = data.get("memory", {})
    if not isinstance(memory_data, dict):
        raise ValueError("memory config must be a TOML table.")

    behavior_data = data.get("behavior", {})
    if not isinstance(behavior_data, dict):
        raise ValueError("behavior config must be a TOML table.")

    voice_data = data.get("voice", {})
    if not isinstance(voice_data, dict):
        raise ValueError("voice config must be a TOML table.")

    return AppConfig(
        pet_window=PetWindowConfig(**pet_window_data),
        ai=AIConfig(**ai_data),
        personality=PersonalityConfig(**personality_data),
        memory=MemoryConfig(**memory_data),
        behavior=BehaviorConfig(**behavior_data),
        voice=VoiceConfig(**voice_data),
    )


def _read_toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8-sig"))


def _deep_merge(
    base: dict[str, Any],
    overlay: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
