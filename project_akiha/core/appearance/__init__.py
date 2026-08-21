"""Trusted complete-appearance contracts."""

from project_akiha.core.appearance.models import (
    AppearanceAvailability,
    AppearanceDefinition,
    AppearanceId,
    AppearanceRegistry,
    AppearanceSelection,
    AppearanceSelectionDecision,
    AppearanceSelectionOutcome,
    AppearanceView,
)
from project_akiha.core.appearance.registry import (
    APPEARANCE_REGISTRY_SCHEMA_VERSION,
    AppearanceRegistryError,
    load_appearance_registry,
)
from project_akiha.core.appearance.repository import AppearanceRepository

__all__ = [
    "APPEARANCE_REGISTRY_SCHEMA_VERSION",
    "AppearanceAvailability",
    "AppearanceDefinition",
    "AppearanceId",
    "AppearanceRegistry",
    "AppearanceRegistryError",
    "AppearanceRepository",
    "AppearanceSelection",
    "AppearanceSelectionDecision",
    "AppearanceSelectionOutcome",
    "AppearanceView",
    "load_appearance_registry",
]
