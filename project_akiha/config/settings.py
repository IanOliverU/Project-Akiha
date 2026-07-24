"""Typed TOML configuration for Project Akiha."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any


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
    request_timeout_seconds: int = 60

    def __post_init__(self) -> None:
        """Validate AI provider settings."""
        if self.provider not in {"mock", "ollama"}:
            raise ValueError("ai.provider must be either 'mock' or 'ollama'.")
        if not self.ollama_base_url:
            raise ValueError("ai.ollama_base_url cannot be empty.")
        if not self.ollama_model:
            raise ValueError("ai.ollama_model cannot be empty.")
        if self.request_timeout_seconds <= 0:
            raise ValueError("ai.request_timeout_seconds must be greater than zero.")


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


@dataclass(frozen=True, slots=True)
class BehaviorConfig:
    """Settings for Phase 4 activity awareness and proactive behavior."""

    enabled: bool = True
    proactive_enabled: bool = False
    idle_after_seconds: int = 300
    away_after_seconds: int = 900
    minimum_seconds_between_notifications: int = 1800
    allow_notifications_while_away: bool = False
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
        _validate_hh_mm(self.quiet_hours_start, "behavior.quiet_hours_start")
        _validate_hh_mm(self.quiet_hours_end, "behavior.quiet_hours_end")


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Full application configuration."""

    pet_window: PetWindowConfig = PetWindowConfig()
    ai: AIConfig = AIConfig()
    personality: PersonalityConfig = PersonalityConfig()
    memory: MemoryConfig = MemoryConfig()
    behavior: BehaviorConfig = BehaviorConfig()

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

    return AppConfig(
        pet_window=PetWindowConfig(**pet_window_data),
        ai=AIConfig(**ai_data),
        personality=PersonalityConfig(**personality_data),
        memory=MemoryConfig(**memory_data),
        behavior=BehaviorConfig(**behavior_data),
    )


def _read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as file:
        return tomllib.load(file)


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
