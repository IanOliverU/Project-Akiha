"""Normalize officially authorized Discord bot events without message text."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from project_akiha.config import DiscordIntegrationConfig
from project_akiha.core.integrations import (
    ExternalClassification,
    ExternalEvent,
    ExternalEventKind,
    ExternalEventPriority,
    ExternalService,
)


class DiscordEventNormalizer:
    """Accept only MESSAGE_CREATE metadata visible to the authorized bot."""

    def __init__(self, config: DiscordIntegrationConfig) -> None:
        self._config = config

    def apply_config(self, config: DiscordIntegrationConfig) -> None:
        """Apply local notification and channel allowlist settings."""
        self._config = config

    def normalize_message_create(
        self,
        payload: object,
        *,
        bot_user_id: str,
        received_at: datetime | None = None,
    ) -> ExternalEvent | None:
        """Return metadata-only event or reject an unauthorized context."""
        if not isinstance(payload, dict):
            return None
        message_id = _snowflake(payload.get("id"))
        channel_id = _snowflake(payload.get("channel_id"))
        raw_guild_id = payload.get("guild_id")
        guild_id = _optional_snowflake(raw_guild_id)
        author = payload.get("author")
        if (
            message_id is None
            or channel_id is None
            or (raw_guild_id is not None and guild_id is None)
            or not isinstance(author, dict)
        ):
            return None
        author_id = _snowflake(author.get("id"))
        if author_id is None or author_id == bot_user_id or author.get("bot") is True:
            return None
        sender = _display_name(author)

        if guild_id is None:
            if not self._config.notify_bot_direct_messages:
                return None
            kind = ExternalEventKind.DISCORD_BOT_DIRECT_MESSAGE
            priority = ExternalEventPriority.NORMAL
        elif _mentions_bot(payload.get("mentions"), bot_user_id):
            if not self._config.notify_mentions:
                return None
            kind = ExternalEventKind.DISCORD_MENTION
            priority = ExternalEventPriority.IMPORTANT
        elif (
            self._config.notify_authorized_channels
            and channel_id in self._config.authorized_channel_ids
        ):
            kind = ExternalEventKind.DISCORD_AUTHORIZED_CHANNEL_MESSAGE
            priority = ExternalEventPriority.NORMAL
        else:
            return None

        return ExternalEvent(
            service=ExternalService.DISCORD,
            external_id=message_id,
            kind=kind,
            occurred_at=_parse_timestamp(payload.get("timestamp"), received_at),
            sender_display=sender,
            context_label=(
                "Direct message" if guild_id is None else "Authorized Discord"
            ),
            classification=ExternalClassification.GENERAL,
            priority=priority,
        )


def _snowflake(value: object) -> str | None:
    if isinstance(value, str) and value.isdecimal() and len(value) <= 32:
        return value
    return None


def _optional_snowflake(value: object) -> str | None:
    return None if value is None else _snowflake(value)


def _display_name(author: dict[str, Any]) -> str | None:
    for key in ("global_name", "username"):
        value = author.get(key)
        if isinstance(value, str):
            normalized = " ".join(value.split())[:160]
            if normalized:
                return normalized
    return None


def _mentions_bot(value: object, bot_user_id: str) -> bool:
    if not isinstance(value, list):
        return False
    return any(
        isinstance(mention, dict) and mention.get("id") == bot_user_id
        for mention in value
    )


def _parse_timestamp(value: object, fallback: datetime | None) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
        else:
            if parsed.tzinfo is not None:
                return parsed
    return fallback or datetime.now(tz=UTC)
