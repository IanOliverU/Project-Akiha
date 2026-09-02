"""Per-event channels layered on top of the existing notification policy."""

from __future__ import annotations

from project_akiha.config import ExternalIntegrationsConfig
from project_akiha.core.integrations import (
    ExternalClassification,
    ExternalEvent,
    ExternalEventKind,
    ExternalEventPriority,
    ExternalService,
)
from project_akiha.core.notifications import (
    NotificationChannelDecision,
    NotificationChannelMode,
)


class ExternalNotificationChannelPolicy:
    """Resolve one closed channel mode from event category and preferences."""

    def evaluate(
        self,
        event: ExternalEvent,
        config: ExternalIntegrationsConfig,
    ) -> NotificationChannelDecision:
        if event.priority == ExternalEventPriority.SILENT:
            return NotificationChannelDecision(False, False, False)
        mode = NotificationChannelMode(self._mode_for_event(event, config))
        tray = mode in {
            NotificationChannelMode.VISUAL_CHAT_VOICE,
            NotificationChannelMode.VISUAL_CHAT,
            NotificationChannelMode.VISUAL_ONLY,
        }
        chat = mode in {
            NotificationChannelMode.VISUAL_CHAT_VOICE,
            NotificationChannelMode.VISUAL_CHAT,
            NotificationChannelMode.CHAT_ONLY,
        }
        voice = mode in {
            NotificationChannelMode.VISUAL_CHAT_VOICE,
            NotificationChannelMode.VOICE_ONLY,
        }
        return NotificationChannelDecision(
            tray=tray and config.visual_notifications_enabled,
            chat=chat and config.chat_notifications_enabled,
            voice=voice and config.voice_notifications_enabled,
        )

    @staticmethod
    def _mode_for_event(
        event: ExternalEvent,
        config: ExternalIntegrationsConfig,
    ) -> str:
        if event.service == ExternalService.GMAIL:
            important = event.priority in {
                ExternalEventPriority.CRITICAL,
                ExternalEventPriority.IMPORTANT,
            } or event.classification in {
                ExternalClassification.IMPORTANT,
                ExternalClassification.WORK,
                ExternalClassification.RECRUITER,
                ExternalClassification.INTERVIEW,
            }
            return (
                config.gmail.important_channel_mode
                if important
                else config.gmail.general_channel_mode
            )
        if event.kind == ExternalEventKind.DISCORD_BOT_DIRECT_MESSAGE:
            return config.discord.direct_message_channel_mode
        if event.kind in {
            ExternalEventKind.DISCORD_MENTION,
            ExternalEventKind.DISCORD_OWNER_MENTION,
            ExternalEventKind.DISCORD_OWNER_REPLY,
        }:
            return config.discord.mention_channel_mode
        return config.discord.authorized_channel_mode
