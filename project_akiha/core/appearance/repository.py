"""Persistence boundary for complete appearance selection."""

from __future__ import annotations

from typing import Protocol

from project_akiha.core.appearance.models import AppearanceSelection


class AppearanceRepository(Protocol):
    """Persist the singleton selected appearance."""

    async def get_selection(self) -> AppearanceSelection:
        """Return the current durable appearance selection."""

    async def save_selection(
        self,
        selection: AppearanceSelection,
    ) -> AppearanceSelection:
        """Replace and return the durable appearance selection."""
