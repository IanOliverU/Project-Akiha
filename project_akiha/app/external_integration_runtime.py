"""Lifecycle owner for optional external communication providers."""

from __future__ import annotations

import logging
from collections.abc import Callable

from project_akiha.config import ExternalIntegrationsConfig
from project_akiha.core.integrations import ExternalEvent, ExternalService
from project_akiha.integrations.discord import DiscordGatewayProvider
from project_akiha.integrations.gmail import GmailIntegrationProvider


class ExternalIntegrationRuntime:
    """Start, reconfigure, refresh, and stop providers independently of Akiha."""

    def __init__(
        self,
        gmail: GmailIntegrationProvider,
        discord: DiscordGatewayProvider,
        on_event: Callable[[ExternalEvent], object],
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._providers = {
            ExternalService.GMAIL: gmail,
            ExternalService.DISCORD: discord,
        }
        self._on_event = on_event
        self._logger = logger or logging.getLogger("project_akiha.integrations.runtime")
        self._started = False

    def start(self) -> None:
        """Start enabled providers without blocking application startup."""
        if self._started:
            return
        self._started = True
        for provider in self._providers.values():
            provider.start(self._on_event)

    def apply_config(self, config: ExternalIntegrationsConfig) -> None:
        """Restart optional workers around a validated settings update."""
        was_started = self._started
        if was_started:
            self.stop()
        self._providers[ExternalService.GMAIL].apply_config(config.gmail)
        self._providers[ExternalService.DISCORD].apply_config(config.discord)
        if was_started:
            self.start()

    def refresh(self, service: ExternalService) -> None:
        """Request one provider refresh when supported."""
        self._providers[service].refresh()

    def health_status(self, service: ExternalService) -> str:
        """Return one privacy-safe status code."""
        return self._providers[service].health_status

    def stop(self) -> None:
        """Stop all providers; one failure cannot block the other."""
        for provider in self._providers.values():
            try:
                provider.stop()
            except Exception:
                self._logger.exception(
                    "External integration provider failed during shutdown."
                )
        self._started = False
