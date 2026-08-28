"""Centralized local wording for privacy-safe external notifications."""

from __future__ import annotations

from project_akiha.core.integrations import (
    ExternalClassification,
    ExternalEvent,
    ExternalEventKind,
    ExternalService,
)


class ExternalNotificationRenderer:
    """Render bounded visual and spoken notices without consulting an LLM."""

    def render(self, event: ExternalEvent) -> str:
        """Return one English desktop notification for a validated event."""
        if event.service == ExternalService.GMAIL:
            return _render_gmail_display(event)
        if event.service == ExternalService.DISCORD:
            return _render_discord_display(event)
        raise ValueError("Unsupported external notification service.")

    def render_speech(self, event: ExternalEvent) -> str:
        """Return one short Japanese line for the existing voice pipeline."""
        if event.service == ExternalService.GMAIL:
            return _render_gmail_speech(event)
        if event.service == ExternalService.DISCORD:
            return _render_discord_speech(event)
        raise ValueError("Unsupported external notification service.")


def _render_gmail_display(event: ExternalEvent) -> str:
    sender = _english_sender(event.sender_display)
    if event.classification == ExternalClassification.INTERVIEW:
        return f"{sender} sent an email that appears related to an interview."
    if event.classification == ExternalClassification.RECRUITER:
        return f"{sender} sent an email that appears to be from a recruiter."
    if (
        event.classification
        in {
            ExternalClassification.IMPORTANT,
            ExternalClassification.WORK,
        }
        or event.kind == ExternalEventKind.GMAIL_IMPORTANT_MESSAGE
    ):
        return f"{sender} sent an email that may be important."
    return f"New email from {sender}."


def _render_discord_display(event: ExternalEvent) -> str:
    sender = event.sender_display or "Someone"
    if event.kind == ExternalEventKind.DISCORD_OWNER_MENTION:
        return f"{sender} mentioned you on Discord."
    if event.kind == ExternalEventKind.DISCORD_OWNER_REPLY:
        return f"{sender} replied to your message on Discord."
    if event.kind == ExternalEventKind.DISCORD_MENTION:
        return f"{sender} mentioned Akiha Bot on Discord."
    if event.kind == ExternalEventKind.DISCORD_BOT_DIRECT_MESSAGE:
        return f"{sender} sent Akiha Bot a direct message."
    return f"New authorized Discord activity from {sender}."


def _render_gmail_speech(event: ExternalEvent) -> str:
    sender = _sender_phrase(event.sender_display)
    if event.classification == ExternalClassification.INTERVIEW:
        return (
            f"Ian-sama\u3001{sender}"
            "\u9762\u63a5\u306b\u95a2\u3059\u308b\u30e1\u30fc\u30eb\u306e"
            "\u3088\u3046\u3067\u3059\u3002"
        )
    if event.classification == ExternalClassification.RECRUITER:
        return (
            f"Ian-sama\u3001{sender}"
            "\u63a1\u7528\u62c5\u5f53\u8005\u304b\u3089\u306e\u30e1\u30fc\u30eb\u306e"
            "\u3088\u3046\u3067\u3059\u3002"
        )
    if (
        event.classification
        in {
            ExternalClassification.IMPORTANT,
            ExternalClassification.WORK,
        }
        or event.kind == ExternalEventKind.GMAIL_IMPORTANT_MESSAGE
    ):
        return (
            f"Ian-sama\u3001{sender}"
            "\u91cd\u8981\u3068\u601d\u308f\u308c\u308b\u30e1\u30fc\u30eb\u304c"
            "\u5c4a\u3044\u3066\u3044\u307e\u3059\u3002"
        )
    return (
        f"Ian-sama\u3001{sender}"
        "\u65b0\u3057\u3044\u30e1\u30fc\u30eb\u304c\u5c4a\u3044\u3066\u3044\u307e\u3059\u3002"
    )


def _render_discord_speech(event: ExternalEvent) -> str:
    if event.kind == ExternalEventKind.DISCORD_OWNER_MENTION:
        return (
            "Ian-sama\u3001Discord\u3067\u3042\u306a\u305f\u3078\u306e"
            "\u30e1\u30f3\u30b7\u30e7\u30f3\u3067\u3059\u3002"
        )
    if event.kind == ExternalEventKind.DISCORD_OWNER_REPLY:
        return (
            "Ian-sama\u3001Discord\u3067\u3042\u306a\u305f\u3078\u306e"
            "\u8fd4\u4fe1\u3067\u3059\u3002"
        )
    if event.kind == ExternalEventKind.DISCORD_MENTION:
        return (
            "Ian-sama\u3001Akiha Bot\u3078\u306eDiscord"
            "\u30e1\u30f3\u30b7\u30e7\u30f3\u3067\u3059\u3002"
        )
    if event.kind == ExternalEventKind.DISCORD_BOT_DIRECT_MESSAGE:
        return (
            "Ian-sama\u3001Akiha Bot\u306bDiscord\u306eDM\u304c"
            "\u5c4a\u304d\u307e\u3057\u305f\u3002"
        )
    return "Ian-sama\u3001Discord\u306b\u65b0\u3057\u3044\u901a\u77e5\u3067\u3059\u3002"


def _sender_phrase(sender_display: str | None) -> str:
    return f"{sender_display}\u304b\u3089\u3001" if sender_display else ""


def _english_sender(sender_display: str | None) -> str:
    return sender_display or "Someone"
