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


def _render_discord(event: ExternalEvent) -> str:
    sender = _sender_phrase(event.sender_display)
    if event.kind == ExternalEventKind.DISCORD_MENTION:
        return (
            f"Ian-sama\u3001{sender}Discord\u3067Akiha\u3078\u306e"
            "\u30e1\u30f3\u30b7\u30e7\u30f3\u304c\u3042\u308a\u307e\u3057\u305f\u3002"
        )
    return (
        f"Ian-sama\u3001{sender}Discord\u306b\u65b0\u3057\u3044"
        "\u30e1\u30c3\u30bb\u30fc\u30b8\u304c\u5c4a\u3044\u3066\u3044\u307e\u3059\u3002"
    )


def _sender_phrase(sender_display: str | None) -> str:
    return f"{sender_display}\u304b\u3089\u3001" if sender_display else ""
