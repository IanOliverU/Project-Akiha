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
class AppConfig:
    """Full application configuration."""

    pet_window: PetWindowConfig = PetWindowConfig()
    ai: AIConfig = AIConfig()

    def with_pet_window(self, pet_window: PetWindowConfig) -> AppConfig:
        """Return a copy with updated pet window settings."""
        return replace(self, pet_window=pet_window)

    def with_ai(self, ai: AIConfig) -> AppConfig:
        """Return a copy with updated AI settings."""
        return replace(self, ai=ai)


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

    return AppConfig(
        pet_window=PetWindowConfig(**pet_window_data),
        ai=AIConfig(**ai_data),
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
