"""Persistence for user-editable configuration overrides."""

from __future__ import annotations

from pathlib import Path

from project_akiha.config import AppConfig


class UserConfigStore:
    """Read and write the user config TOML file."""

    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path

    @property
    def config_path(self) -> Path:
        """Return the user config file path."""
        return self._config_path

    def save_config(self, config: AppConfig) -> None:
        """Persist supported config values as TOML."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._config_path.with_suffix(".tmp")
        temporary_path.write_text(_serialize_config(config), encoding="utf-8")
        temporary_path.replace(self._config_path)


def _serialize_config(config: AppConfig) -> str:
    pet_window = config.pet_window
    ai = config.ai
    personality = config.personality
    memory = config.memory
    always_on_top = str(pet_window.always_on_top).lower()
    memory_enabled = str(memory.enabled).lower()
    manifest_path = _escape_toml_string(pet_window.animation_manifest_path)
    provider = _escape_toml_string(ai.provider)
    ollama_base_url = _escape_toml_string(ai.ollama_base_url)
    ollama_model = _escape_toml_string(ai.ollama_model)
    character_name = _escape_toml_string(personality.character_name)
    system_prompt = _escape_toml_string(personality.system_prompt)

    return (
        "[pet_window]\n"
        f"width = {pet_window.width}\n"
        f"height = {pet_window.height}\n"
        f"frames_per_second = {pet_window.frames_per_second}\n"
        f"start_x = {pet_window.start_x}\n"
        f"start_y = {pet_window.start_y}\n"
        f"always_on_top = {always_on_top}\n"
        f'animation_manifest_path = "{manifest_path}"\n'
        f"walking_speed_pixels = {pet_window.walking_speed_pixels}\n"
        "\n"
        "[ai]\n"
        f'provider = "{provider}"\n'
        f'ollama_base_url = "{ollama_base_url}"\n'
        f'ollama_model = "{ollama_model}"\n'
        f"request_timeout_seconds = {ai.request_timeout_seconds}\n"
        "\n"
        "[personality]\n"
        f'character_name = "{character_name}"\n'
        f'system_prompt = "{system_prompt}"\n'
        "\n"
        "[memory]\n"
        f"enabled = {memory_enabled}\n"
    )


def _escape_toml_string(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
