"""Centralized local wording for privacy-safe external notifications."""

from __future__ import annotations

from project_akiha.core.integrations import (
    ExternalClassification,
    ExternalEvent,
    ExternalEventKind,
    ExternalService,
)


class ExternalNotificationRenderer:
    """Render bounded Akiha-style notices without consulting an LLM."""

    def render(self, event: ExternalEvent) -> str:
        """Return one local notification line for a validated event."""
        if event.service == ExternalService.GMAIL:
            return _render_gmail(event)
        if event.service == ExternalService.DISCORD:
            return _render_discord(event)
        raise ValueError("Unsupported external notification service.")


def _render_gmail(event: ExternalEvent) -> str:
    sender = _sender_phrase(event.sender_display)
    if event.classification == ExternalClassification.INTERVIEW:
        return f"Ian-sama、{sender}面接に関するメールのようです。"
    if event.classification == ExternalClassification.RECRUITER:
        return f"Ian-sama、{sender}採用担当者からのメールのようです。"
    if (
        event.classification
        in {
            ExternalClassification.IMPORTANT,
            ExternalClassification.WORK,
        }
        or event.kind == ExternalEventKind.GMAIL_IMPORTANT_MESSAGE
    ):
        return f"Ian-sama、{sender}重要と思われるメールが届いています。"
    return f"Ian-sama、{sender}新しいメールが届いています。"


def _render_discord(event: ExternalEvent) -> str:
    sender = _sender_phrase(event.sender_display)
    if event.kind == ExternalEventKind.DISCORD_MENTION:
        return f"Ian-sama、{sender}Discordであなたへのメンションがありました。"
    if event.kind == ExternalEventKind.DISCORD_FRIEND_REQUEST_CANDIDATE:
        return f"Ian-sama、{sender}Discordでフレンド申請が届いたようです。"
    return f"Ian-sama、{sender}Discordに新しいメッセージが届いています。"


def _sender_phrase(sender_display: str | None) -> str:
    return f"{sender_display}から、" if sender_display else ""
