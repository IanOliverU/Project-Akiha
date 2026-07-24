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
    behavior = config.behavior
    always_on_top = str(pet_window.always_on_top).lower()
    memory_enabled = str(memory.enabled).lower()
    behavior_enabled = str(behavior.enabled).lower()
    proactive_enabled = str(behavior.proactive_enabled).lower()
    allow_notifications_while_away = str(
        behavior.allow_notifications_while_away
    ).lower()
    scheduled_check_ins_enabled = str(behavior.scheduled_check_ins_enabled).lower()
    quiet_hours_enabled = str(behavior.quiet_hours_enabled).lower()
    manifest_path = _escape_toml_string(pet_window.animation_manifest_path)
    provider = _escape_toml_string(ai.provider)
    ollama_base_url = _escape_toml_string(ai.ollama_base_url)
    ollama_model = _escape_toml_string(ai.ollama_model)
    character_name = _escape_toml_string(personality.character_name)
    system_prompt = _escape_toml_string(personality.system_prompt)
    quiet_hours_start = _escape_toml_string(behavior.quiet_hours_start)
    quiet_hours_end = _escape_toml_string(behavior.quiet_hours_end)

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
        f"retrieval_limit = {memory.retrieval_limit}\n"
        f"require_approval = {str(memory.require_approval).lower()}\n"
        "\n"
        "[behavior]\n"
        f"enabled = {behavior_enabled}\n"
        f"proactive_enabled = {proactive_enabled}\n"
        f"idle_after_seconds = {behavior.idle_after_seconds}\n"
        f"away_after_seconds = {behavior.away_after_seconds}\n"
        "minimum_seconds_between_notifications = "
        f"{behavior.minimum_seconds_between_notifications}\n"
        f"allow_notifications_while_away = {allow_notifications_while_away}\n"
        f"scheduled_check_ins_enabled = {scheduled_check_ins_enabled}\n"
        "scheduled_check_in_interval_seconds = "
        f"{behavior.scheduled_check_in_interval_seconds}\n"
        f"quiet_hours_enabled = {quiet_hours_enabled}\n"
        f'quiet_hours_start = "{quiet_hours_start}"\n'
        f'quiet_hours_end = "{quiet_hours_end}"\n'
    )


def _escape_toml_string(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
