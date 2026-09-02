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
    privacy = config.privacy
    behavior = config.behavior
    voice = config.voice
    spotify = config.spotify
    integrations = config.integrations
    gmail = integrations.gmail
    discord = integrations.discord
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
    hosted_base_url = _escape_toml_string(ai.hosted_base_url)
    hosted_model = _escape_toml_string(ai.hosted_model)
    character_name = _escape_toml_string(personality.character_name)
    system_prompt = _escape_toml_string(personality.system_prompt)
    quiet_hours_start = _escape_toml_string(behavior.quiet_hours_start)
    quiet_hours_end = _escape_toml_string(behavior.quiet_hours_end)
    voice_input_provider = _escape_toml_string(voice.input_provider)
    voice_input_model = _escape_toml_string(voice.input_model)
    voice_input_language = _escape_toml_string(voice.input_language)
    voice_input_device = _escape_toml_string(voice.input_device)
    voice_output_provider = _escape_toml_string(voice.output_provider)
    voice_output_base_url = _escape_toml_string(voice.output_base_url)
    voice_output_voice_id = _escape_toml_string(voice.output_voice_id)
    voice_output_reference_dir = _escape_toml_string(voice.output_reference_dir)
    voice_output_prompt_text = _escape_toml_string(voice.output_prompt_text)
    voice_output_device = _escape_toml_string(voice.output_device)
    voice_session_provider = _escape_toml_string(voice.session_provider)
    hosted_live_model = _escape_toml_string(voice.hosted_live_model)
    hosted_live_voice_name = _escape_toml_string(voice.hosted_live_voice_name)
    spotify_client_id = _escape_toml_string(spotify.client_id)
    spotify_redirect_uri = _escape_toml_string(spotify.redirect_uri)
    gmail_client_id = _escape_toml_string(gmail.client_id)
    gmail_redirect_uri = _escape_toml_string(gmail.redirect_uri)
    discord_channel_ids = ", ".join(
        f'"{_escape_toml_string(value)}"' for value in discord.authorized_channel_ids
    )

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
        f'hosted_base_url = "{hosted_base_url}"\n'
        f'hosted_model = "{hosted_model}"\n'
        f"request_timeout_seconds = {ai.request_timeout_seconds}\n"
        f"assistant_tools_enabled = {str(ai.assistant_tools_enabled).lower()}\n"
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
        "[privacy]\n"
        "notice_version_acknowledged = "
        f"{privacy.notice_version_acknowledged}\n"
        "hosted_live_notice_version_acknowledged = "
        f"{privacy.hosted_live_notice_version_acknowledged}\n"
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
        "\n"
        "[voice]\n"
        f"enabled = {str(voice.enabled).lower()}\n"
        f"push_to_talk_enabled = {str(voice.push_to_talk_enabled).lower()}\n"
        f'input_provider = "{voice_input_provider}"\n'
        f'input_model = "{voice_input_model}"\n'
        f'input_language = "{voice_input_language}"\n'
        f'input_device = "{voice_input_device}"\n'
        f'output_provider = "{voice_output_provider}"\n'
        f'output_base_url = "{voice_output_base_url}"\n'
        f'output_voice_id = "{voice_output_voice_id}"\n'
        f'output_reference_dir = "{voice_output_reference_dir}"\n'
        f'output_prompt_text = "{voice_output_prompt_text}"\n'
        f'output_device = "{voice_output_device}"\n'
        "output_engine_auto_start = "
        f"{str(voice.output_engine_auto_start).lower()}\n"
        "output_engine_stop_on_exit = "
        f"{str(voice.output_engine_stop_on_exit).lower()}\n"
        "automatic_speech_enabled = "
        f"{str(voice.automatic_speech_enabled).lower()}\n"
        "proactive_speech_enabled = "
        f"{str(voice.proactive_speech_enabled).lower()}\n"
        "english_subtitles_enabled = "
        f"{str(voice.english_subtitles_enabled).lower()}\n"
        "export_english_subtitles_enabled = "
        f"{str(voice.export_english_subtitles_enabled).lower()}\n"
        "live_transcription_enabled = "
        f"{str(voice.live_transcription_enabled).lower()}\n"
        "auto_stop_on_silence_enabled = "
        f"{str(voice.auto_stop_on_silence_enabled).lower()}\n"
        "auto_send_transcript_enabled = "
        f"{str(voice.auto_send_transcript_enabled).lower()}\n"
        f"silence_timeout_seconds = {voice.silence_timeout_seconds}\n"
        f"volume_percent = {voice.volume_percent}\n"
        f"speaking_rate = {voice.speaking_rate}\n"
        f"capture_timeout_seconds = {voice.capture_timeout_seconds}\n"
        f"request_timeout_seconds = {voice.request_timeout_seconds}\n"
        "local_conversation_idle_timeout_seconds = "
        f"{voice.local_conversation_idle_timeout_seconds}\n"
        "local_conversation_max_duration_seconds = "
        f"{voice.local_conversation_max_duration_seconds}\n"
        f'session_provider = "{voice_session_provider}"\n'
        f'hosted_live_model = "{hosted_live_model}"\n'
        f'hosted_live_voice_name = "{hosted_live_voice_name}"\n'
        "hosted_live_max_duration_seconds = "
        f"{voice.hosted_live_max_duration_seconds}\n"
        "\n"
        "[spotify]\n"
        f"enabled = {str(spotify.enabled).lower()}\n"
        f'client_id = "{spotify_client_id}"\n'
        f'redirect_uri = "{spotify_redirect_uri}"\n'
        "auto_launch_desktop_app = "
        f"{str(spotify.auto_launch_desktop_app).lower()}\n"
        f"request_timeout_seconds = {spotify.request_timeout_seconds}\n"
        "\n"
        "[integrations]\n"
        "visual_notifications_enabled = "
        f"{str(integrations.visual_notifications_enabled).lower()}\n"
        "chat_notifications_enabled = "
        f"{str(integrations.chat_notifications_enabled).lower()}\n"
        "voice_notifications_enabled = "
        f"{str(integrations.voice_notifications_enabled).lower()}\n"
        "notification_cooldown_seconds = "
        f"{integrations.notification_cooldown_seconds}\n"
        f"event_expiry_seconds = {integrations.event_expiry_seconds}\n"
        f"receipt_retention_days = {integrations.receipt_retention_days}\n"
        "\n"
        "[integrations.gmail]\n"
        f"enabled = {str(gmail.enabled).lower()}\n"
        f'client_id = "{gmail_client_id}"\n'
        f'redirect_uri = "{gmail_redirect_uri}"\n'
        f"poll_interval_seconds = {gmail.poll_interval_seconds}\n"
        f"request_timeout_seconds = {gmail.request_timeout_seconds}\n"
        f"notify_new_messages = {str(gmail.notify_new_messages).lower()}\n"
        f"notify_important = {str(gmail.notify_important).lower()}\n"
        f"notify_interview = {str(gmail.notify_interview).lower()}\n"
        f"notify_recruiter = {str(gmail.notify_recruiter).lower()}\n"
        f"notify_work = {str(gmail.notify_work).lower()}\n"
        f"notify_personal = {str(gmail.notify_personal).lower()}\n"
        f"notify_newsletter = {str(gmail.notify_newsletter).lower()}\n"
        f"notify_promotional = {str(gmail.notify_promotional).lower()}\n"
        "general_channel_mode = "
        f'"{_escape_toml_string(gmail.general_channel_mode)}"\n'
        "important_channel_mode = "
        f'"{_escape_toml_string(gmail.important_channel_mode)}"\n'
        "\n"
        "[integrations.discord]\n"
        f"enabled = {str(discord.enabled).lower()}\n"
        f'mode = "{_escape_toml_string(discord.mode)}"\n'
        "notify_bot_direct_messages = "
        f"{str(discord.notify_bot_direct_messages).lower()}\n"
        f"notify_mentions = {str(discord.notify_mentions).lower()}\n"
        "notify_owner_mentions = "
        f"{str(discord.notify_owner_mentions).lower()}\n"
        "notify_owner_replies = "
        f"{str(discord.notify_owner_replies).lower()}\n"
        f'owner_user_id = "{_escape_toml_string(discord.owner_user_id)}"\n'
        "notify_authorized_channels = "
        f"{str(discord.notify_authorized_channels).lower()}\n"
        f"authorized_channel_ids = [{discord_channel_ids}]\n"
        f"reconnect_max_seconds = {discord.reconnect_max_seconds}\n"
        "direct_message_channel_mode = "
        f'"{_escape_toml_string(discord.direct_message_channel_mode)}"\n'
        "mention_channel_mode = "
        f'"{_escape_toml_string(discord.mention_channel_mode)}"\n'
        "authorized_channel_mode = "
        f'"{_escape_toml_string(discord.authorized_channel_mode)}"\n'
    )


def _escape_toml_string(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
