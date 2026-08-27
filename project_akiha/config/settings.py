"""Typed TOML configuration for Project Akiha."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, replace
from ipaddress import ip_address
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

SPOTIFY_REDIRECT_URI = "http://127.0.0.1:43821/callback"
GMAIL_REDIRECT_URI = "http://127.0.0.1:43822/callback"
_SPOTIFY_CLIENT_ID_PATTERN = re.compile(r"[0-9a-fA-F]{32}\Z")


def ai_text_processing_is_remote(provider: str, provider_base_url: str) -> bool:
    """Classify whether the selected AI transport sends text off-device."""
    if provider == "mock":
        return False
    if provider in {"ollama", "openai-compatible"}:
        return not _is_loopback_url(provider_base_url)
    return provider in HOSTED_AI_PROVIDERS


def _is_loopback_url(value: str) -> bool:
    hostname = urlparse(value).hostname
    if hostname is None:
        return False
    if hostname.casefold() == "localhost":
        return True
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True, slots=True)
class PetWindowConfig:
    """Settings that control the Phase 1 desktop pet window."""

    width: int = 180
    height: int = 220
    frames_per_second: int = 30
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
    assistant_tools_enabled: bool = False

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

    @property
    def sends_text_off_device(self) -> bool:
        """Return whether chat text may leave the current device."""
        return ai_text_processing_is_remote(
            self.provider,
            (
                self.ollama_base_url
                if self.provider == "ollama"
                else self.hosted_base_url
            ),
        )


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


@dataclass(frozen=True, slots=True)
class PrivacyConfig:
    """Versioned acknowledgement state for privacy notices."""

    notice_version_acknowledged: int = 0
    hosted_live_notice_version_acknowledged: int = 0

    def __post_init__(self) -> None:
        """Reject invalid persisted notice versions."""
        if self.notice_version_acknowledged < 0:
            raise ValueError("privacy.notice_version_acknowledged cannot be negative.")
        if self.hosted_live_notice_version_acknowledged < 0:
            raise ValueError(
                "privacy.hosted_live_notice_version_acknowledged cannot be negative."
            )


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
    output_provider: str = "gpt-sovits"
    output_base_url: str = "http://127.0.0.1:9880"
    output_voice_id: str = "akiha"
    output_reference_dir: str = "AKIHA VOICE"
    output_prompt_text: str = ""
    output_device: str = ""
    output_engine_auto_start: bool = False
    output_engine_stop_on_exit: bool = True
    automatic_speech_enabled: bool = False
    proactive_speech_enabled: bool = False
    english_subtitles_enabled: bool = False
    export_english_subtitles_enabled: bool = False
    live_transcription_enabled: bool = False
    auto_stop_on_silence_enabled: bool = False
    auto_send_transcript_enabled: bool = False
    silence_timeout_seconds: float = 1.2
    volume_percent: int = 100
    speaking_rate: float = 1.0
    capture_timeout_seconds: int = 30
    request_timeout_seconds: int = 30
    local_conversation_idle_timeout_seconds: int = 120
    local_conversation_max_duration_seconds: int = 1800
    session_provider: str = "local_modular"
    hosted_live_model: str = "gemini-3.1-flash-live-preview"
    hosted_live_voice_name: str = "Kore"
    hosted_live_max_duration_seconds: int = 600

    def __post_init__(self) -> None:
        """Validate provider-neutral voice settings."""
        if self.input_provider not in {"disabled", "faster-whisper"}:
            message = (
                "voice.input_provider must be either 'disabled' or " "'faster-whisper'."
            )
            raise ValueError(message)
        if self.output_provider not in {
            "disabled",
            "gpt-sovits",
        }:
            message = "voice.output_provider must be 'disabled' or 'gpt-sovits'."
            raise ValueError(message)
        if not self.input_model.strip():
            raise ValueError("voice.input_model cannot be empty.")
        if not self.input_language.strip():
            raise ValueError("voice.input_language cannot be empty.")
        if not self.output_voice_id.strip():
            raise ValueError("voice.output_voice_id cannot be empty.")
        if not self.output_reference_dir.strip():
            raise ValueError("voice.output_reference_dir cannot be empty.")
        if "\n" in self.output_reference_dir or "\r" in self.output_reference_dir:
            raise ValueError("voice.output_reference_dir must be a single line.")
        if "\n" in self.output_prompt_text or "\r" in self.output_prompt_text:
            raise ValueError("voice.output_prompt_text must be a single line.")
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
        if not 15 <= self.local_conversation_idle_timeout_seconds <= 1800:
            raise ValueError(
                "voice.local_conversation_idle_timeout_seconds must be between "
                "15 and 1800."
            )
        if not 60 <= self.local_conversation_max_duration_seconds <= 14400:
            raise ValueError(
                "voice.local_conversation_max_duration_seconds must be between "
                "60 and 14400."
            )
        if self.session_provider not in {"local_modular", "gemini_live"}:
            raise ValueError(
                "voice.session_provider must be 'local_modular' or 'gemini_live'."
            )
        if not self.hosted_live_model.strip():
            raise ValueError("voice.hosted_live_model cannot be empty.")
        if not self.hosted_live_voice_name.strip():
            raise ValueError("voice.hosted_live_voice_name cannot be empty.")
        if self.hosted_live_max_duration_seconds not in {300, 600, 900}:
            raise ValueError(
                "voice.hosted_live_max_duration_seconds must be 300, 600, or 900."
            )

    @property
    def input_enabled(self) -> bool:
        """Return whether speech input may be used."""
        return self.enabled and self.input_provider != "disabled"

    @property
    def output_enabled(self) -> bool:
        """Return whether speech output may be used."""
        return self.enabled and self.output_provider != "disabled"


@dataclass(frozen=True, slots=True)
class SpotifyConfig:
    """Settings for the optional local Spotify Web API integration."""

    enabled: bool = False
    client_id: str = ""
    redirect_uri: str = SPOTIFY_REDIRECT_URI
    auto_launch_desktop_app: bool = True
    request_timeout_seconds: int = 15

    def __post_init__(self) -> None:
        """Validate public OAuth metadata without accepting arbitrary callbacks."""
        client_id = self.client_id.strip()
        if client_id and _SPOTIFY_CLIENT_ID_PATTERN.fullmatch(client_id) is None:
            raise ValueError("spotify.client_id must be a 32-character hexadecimal ID.")
        if self.enabled and not client_id:
            raise ValueError("spotify.client_id is required when Spotify is enabled.")
        if self.redirect_uri != SPOTIFY_REDIRECT_URI:
            raise ValueError(f"spotify.redirect_uri must be {SPOTIFY_REDIRECT_URI}.")
        if self.request_timeout_seconds <= 0:
            raise ValueError(
                "spotify.request_timeout_seconds must be greater than zero."
            )


@dataclass(frozen=True, slots=True)
class GmailIntegrationConfig:
    """Settings for optional metadata-only Gmail awareness."""

    enabled: bool = False
    client_id: str = ""
    redirect_uri: str = GMAIL_REDIRECT_URI
    poll_interval_seconds: int = 60
    request_timeout_seconds: int = 15
    notify_new_messages: bool = True
    notify_important: bool = True
    notify_interview: bool = True
    notify_recruiter: bool = True
    notify_work: bool = True
    notify_personal: bool = False
    notify_newsletter: bool = False
    notify_promotional: bool = False

    def __post_init__(self) -> None:
        """Validate public desktop OAuth configuration."""
        client_id = self.client_id.strip()
        if client_id and (
            len(client_id) > 256
            or not client_id.endswith(".apps.googleusercontent.com")
        ):
            raise ValueError(
                "integrations.gmail.client_id must be a Google Desktop OAuth "
                "client ID."
            )
        if self.enabled and not client_id:
            raise ValueError(
                "integrations.gmail.client_id is required when Gmail is enabled."
            )
        if self.redirect_uri != GMAIL_REDIRECT_URI:
            raise ValueError(
                f"integrations.gmail.redirect_uri must be {GMAIL_REDIRECT_URI}."
            )
        if not 30 <= self.poll_interval_seconds <= 3600:
            raise ValueError(
                "integrations.gmail.poll_interval_seconds must be between 30 "
                "and 3600."
            )
        if not 1 <= self.request_timeout_seconds <= 60:
            raise ValueError(
                "integrations.gmail.request_timeout_seconds must be between 1 "
                "and 60."
            )


@dataclass(frozen=True, slots=True)
class DiscordIntegrationConfig:
    """Settings for the constrained official Discord bot/Gateway mode."""

    enabled: bool = False
    mode: str = "bot_gateway"
    notify_bot_direct_messages: bool = True
    notify_mentions: bool = True
    notify_authorized_channels: bool = False
    authorized_channel_ids: tuple[str, ...] = ()
    reconnect_max_seconds: int = 60

    def __post_init__(self) -> None:
        """Reject unsupported personal-account modes and invalid channel IDs."""
        if self.mode != "bot_gateway":
            raise ValueError(
                "integrations.discord.mode must be 'bot_gateway'; self-bot "
                "modes are unsupported."
            )
        normalized_ids = tuple(
            dict.fromkeys(
                value.strip() for value in self.authorized_channel_ids if value.strip()
            )
        )
        if any(not value.isdecimal() or len(value) > 32 for value in normalized_ids):
            raise ValueError(
                "integrations.discord.authorized_channel_ids must contain "
                "Discord snowflake IDs."
            )
        if not 5 <= self.reconnect_max_seconds <= 300:
            raise ValueError(
                "integrations.discord.reconnect_max_seconds must be between 5 "
                "and 300."
            )
        object.__setattr__(self, "authorized_channel_ids", normalized_ids)


@dataclass(frozen=True, slots=True)
class ExternalIntegrationsConfig:
    """Shared external-awareness preferences and provider settings."""

    visual_notifications_enabled: bool = True
    voice_notifications_enabled: bool = True
    event_expiry_seconds: int = 300
    receipt_retention_days: int = 90
    gmail: GmailIntegrationConfig = GmailIntegrationConfig()
    discord: DiscordIntegrationConfig = DiscordIntegrationConfig()

    def __post_init__(self) -> None:
        """Validate shared external notification limits."""
        if not 30 <= self.event_expiry_seconds <= 3600:
            raise ValueError(
                "integrations.event_expiry_seconds must be between 30 and 3600."
            )
        if not 1 <= self.receipt_retention_days <= 365:
            raise ValueError(
                "integrations.receipt_retention_days must be between 1 and 365."
            )


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Full application configuration."""

    pet_window: PetWindowConfig = PetWindowConfig()
    ai: AIConfig = AIConfig()
    personality: PersonalityConfig = PersonalityConfig()
    memory: MemoryConfig = MemoryConfig()
    privacy: PrivacyConfig = PrivacyConfig()
    behavior: BehaviorConfig = BehaviorConfig()
    voice: VoiceConfig = VoiceConfig()
    spotify: SpotifyConfig = SpotifyConfig()
    integrations: ExternalIntegrationsConfig = ExternalIntegrationsConfig()

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

    def with_privacy(self, privacy: PrivacyConfig) -> AppConfig:
        """Return a copy with updated privacy acknowledgement state."""
        return replace(self, privacy=privacy)

    def with_behavior(self, behavior: BehaviorConfig) -> AppConfig:
        """Return a copy with updated behavior settings."""
        return replace(self, behavior=behavior)

    def with_voice(self, voice: VoiceConfig) -> AppConfig:
        """Return a copy with updated voice settings."""
        return replace(self, voice=voice)

    def with_spotify(self, spotify: SpotifyConfig) -> AppConfig:
        """Return a copy with updated Spotify integration settings."""
        return replace(self, spotify=spotify)

    def with_integrations(
        self,
        integrations: ExternalIntegrationsConfig,
    ) -> AppConfig:
        """Return a copy with updated external integration settings."""
        return replace(self, integrations=integrations)


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

    privacy_data = data.get("privacy", {})
    if not isinstance(privacy_data, dict):
        raise ValueError("privacy config must be a TOML table.")

    behavior_data = data.get("behavior", {})
    if not isinstance(behavior_data, dict):
        raise ValueError("behavior config must be a TOML table.")

    voice_data = data.get("voice", {})
    if not isinstance(voice_data, dict):
        raise ValueError("voice config must be a TOML table.")
    legacy_voice_provider = voice_data.get("output_provider")
    if legacy_voice_provider in {"akiha-chatterbox", "voicevox"}:
        # Preserve existing user configurations while making GPT-SoVITS the
        # permanent local voice backend.
        voice_data = dict(voice_data)
        voice_data["output_provider"] = "gpt-sovits"
        voice_data["output_base_url"] = "http://127.0.0.1:9880"
    if "output_engine_path" in voice_data:
        # The old path selected a standalone VOICEVOX executable. GPT-SoVITS
        # resolves its managed runtime from the project and environment.
        voice_data = dict(voice_data)
        voice_data.pop("output_engine_path", None)

    spotify_data = data.get("spotify", {})
    if not isinstance(spotify_data, dict):
        raise ValueError("spotify config must be a TOML table.")

    integrations_data = data.get("integrations", {})
    if not isinstance(integrations_data, dict):
        raise ValueError("integrations config must be a TOML table.")
    integrations_data = dict(integrations_data)
    gmail_data = integrations_data.pop("gmail", {})
    discord_data = integrations_data.pop("discord", {})
    if not isinstance(gmail_data, dict):
        raise ValueError("integrations.gmail config must be a TOML table.")
    if not isinstance(discord_data, dict):
        raise ValueError("integrations.discord config must be a TOML table.")

    return AppConfig(
        pet_window=PetWindowConfig(**pet_window_data),
        ai=AIConfig(**ai_data),
        personality=PersonalityConfig(**personality_data),
        memory=MemoryConfig(**memory_data),
        privacy=PrivacyConfig(**privacy_data),
        behavior=BehaviorConfig(**behavior_data),
        voice=VoiceConfig(**voice_data),
        spotify=SpotifyConfig(**spotify_data),
        integrations=ExternalIntegrationsConfig(
            **integrations_data,
            gmail=GmailIntegrationConfig(**gmail_data),
            discord=DiscordIntegrationConfig(**discord_data),
        ),
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
