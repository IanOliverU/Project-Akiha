"""Safe delivery routing for proactive companion suggestions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from project_akiha.core.behavior.notification_policy import NotificationUrgency


class DeliveryChannel(StrEnum):
    """Where a proactive suggestion was delivered."""

    CHAT_NOTICE = "chat_notice"
    TRAY_MESSAGE = "tray_message"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class ProactiveDeliveryRequest:
    """A suggestion ready to be surfaced to the user."""

    kind: str
    message: str
    urgency: NotificationUrgency
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ProactiveDeliveryResult:
    """Outcome of a proactive delivery attempt."""

    delivered: bool
    channel: DeliveryChannel
    reason: str
    request: ProactiveDeliveryRequest


class ProactiveDeliverySurface(Protocol):
    """UI surface used by the delivery service."""

    def is_chat_visible(self) -> bool:
        """Return whether chat is currently visible to the user."""

    def append_chat_notice(self, message: str) -> None:
        """Append a quiet notice to chat."""

    def can_show_tray_message(self) -> bool:
        """Return whether tray messages are available."""

    def show_tray_message(self, title: str, message: str) -> None:
        """Show a non-modal tray message."""


class ProactiveDeliveryService:
    """Deliver proactive suggestions without stealing focus."""

    _title = "Akiha"

    def deliver(
        self,
        request: ProactiveDeliveryRequest,
        surface: ProactiveDeliverySurface,
    ) -> ProactiveDeliveryResult:
        """Deliver the suggestion to the safest available surface."""
        if not request.message.strip():
            return ProactiveDeliveryResult(
                delivered=False,
                channel=DeliveryChannel.NONE,
                reason="empty_message",
                request=request,
            )

        if surface.is_chat_visible():
            surface.append_chat_notice(request.message)
            return ProactiveDeliveryResult(
                delivered=True,
                channel=DeliveryChannel.CHAT_NOTICE,
                reason="chat_visible",
                request=request,
            )

        if surface.can_show_tray_message():
            surface.show_tray_message(self._title, request.message)
            return ProactiveDeliveryResult(
                delivered=True,
                channel=DeliveryChannel.TRAY_MESSAGE,
                reason="chat_hidden",
                request=request,
            )

        return ProactiveDeliveryResult(
            delivered=False,
            channel=DeliveryChannel.NONE,
            reason="no_available_surface",
            request=request,
        )
