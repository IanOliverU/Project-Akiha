"""Read-only Akiha status and privacy-safe Phase 10 diagnostics."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from project_akiha.core.appearance import (
    AppearanceAvailability,
    AppearanceId,
    AppearanceView,
)
from project_akiha.core.behavior import ActivityState, CompanionMood
from project_akiha.core.pet import PetStateRecord
from project_akiha.core.pet_activity import PetActivityDefinition, PetActivityId
from project_akiha.core.shop import (
    CatalogAvailability,
    CatalogLoadResult,
    ShopRepository,
)
from project_akiha.core.state.animation import AnimationState
from project_akiha.services.appearance import AppearanceService
from project_akiha.services.pet_diagnostics import (
    PetDiagnosticsSnapshot,
    build_pet_diagnostics,
)


class PetSnapshotService(Protocol):
    """Minimal read-only pet-state dependency."""

    async def snapshot(self) -> PetStateRecord:
        """Return the current validated pet-state record."""


@dataclass(frozen=True, slots=True)
class PetRuntimeStatus:
    """Typed in-memory state that is safe to show in the Status surface."""

    mood: CompanionMood
    user_activity: ActivityState
    animation_state: AnimationState
    autonomous_activity_id: PetActivityId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mood, CompanionMood):
            raise TypeError("mood must be a CompanionMood value.")
        if not isinstance(self.user_activity, ActivityState):
            raise TypeError("user_activity must be an ActivityState value.")
        if not isinstance(self.animation_state, AnimationState):
            raise TypeError("animation_state must be an AnimationState value.")
        if self.autonomous_activity_id is not None and not isinstance(
            self.autonomous_activity_id, PetActivityId
        ):
            raise TypeError(
                "autonomous_activity_id must be a PetActivityId value or None."
            )


@dataclass(frozen=True, slots=True)
class Phase10PrivacyBoundary:
    """Explicit capabilities that Phase 10 intentionally does not provide."""

    real_money_store: bool = False
    telemetry: bool = False
    cloud_asset_upload: bool = False
    remote_marketplace: bool = False

    def __post_init__(self) -> None:
        for value in (
            self.real_money_store,
            self.telemetry,
            self.cloud_asset_upload,
            self.remote_marketplace,
        ):
            if type(value) is not bool:
                raise TypeError("privacy capability flags must be boolean values.")

    @property
    def local_only(self) -> bool:
        """Return whether every prohibited remote/store capability is absent."""
        return not any(
            (
                self.real_money_store,
                self.telemetry,
                self.cloud_asset_upload,
                self.remote_marketplace,
            )
        )


PHASE10_PRIVACY_BOUNDARY = Phase10PrivacyBoundary()


@dataclass(frozen=True, slots=True)
class PetSystemDiagnostics:
    """Bounded local diagnostics without dialogue, credentials, or asset paths."""

    catalog_version: int
    catalog_item_count: int
    available_catalog_item_count: int
    catalog_failure: str | None
    owned_item_count: int
    transaction_count: int
    last_purchase_at: datetime | None
    appearance_count: int
    available_appearance_count: int
    owned_appearance_count: int
    current_appearance_id: AppearanceId
    activity_definition_count: int
    active_activity_id: PetActivityId | None
    privacy: Phase10PrivacyBoundary = PHASE10_PRIVACY_BOUNDARY

    def __post_init__(self) -> None:
        for value in (
            self.catalog_version,
            self.catalog_item_count,
            self.available_catalog_item_count,
            self.owned_item_count,
            self.transaction_count,
            self.appearance_count,
            self.available_appearance_count,
            self.owned_appearance_count,
            self.activity_definition_count,
        ):
            if type(value) is not int or value < 0:
                raise ValueError("diagnostic counts must be nonnegative integers.")
        if self.catalog_version <= 0:
            raise ValueError("catalog_version must be positive.")
        if self.catalog_failure is not None and not isinstance(
            self.catalog_failure, str
        ):
            raise TypeError("catalog_failure must be a string or None.")
        if self.last_purchase_at is not None and (
            self.last_purchase_at.tzinfo is None
            or self.last_purchase_at.utcoffset() is None
        ):
            raise ValueError("last_purchase_at must be timezone-aware.")
        if not isinstance(self.current_appearance_id, AppearanceId):
            raise TypeError("current_appearance_id must be an AppearanceId value.")
        if self.active_activity_id is not None and not isinstance(
            self.active_activity_id, PetActivityId
        ):
            raise TypeError("active_activity_id must be a PetActivityId value or None.")
        if not isinstance(self.privacy, Phase10PrivacyBoundary):
            raise TypeError("privacy must be a Phase10PrivacyBoundary value.")

    @property
    def catalog_summary(self) -> str:
        health = "ready" if self.catalog_failure is None else "safe fallback"
        return (
            f"Version {self.catalog_version} | {self.catalog_item_count} products | "
            f"{self.available_catalog_item_count} available | {health}"
        )

    @property
    def ownership_summary(self) -> str:
        return (
            f"{self.owned_item_count} owned items | "
            f"{self.transaction_count} completed transactions"
        )

    @property
    def transaction_summary(self) -> str:
        latest = self.last_purchase_at.isoformat() if self.last_purchase_at else "none"
        return f"{self.transaction_count} completed | latest {latest}"

    @property
    def appearance_summary(self) -> str:
        availability = (
            f"{self.available_appearance_count}/{self.appearance_count} sets available"
        )
        return (
            f"{self.current_appearance_id.value} selected | "
            f"{availability} | "
            f"{self.owned_appearance_count} owned"
        )

    @property
    def activity_summary(self) -> str:
        active = self.active_activity_id.value if self.active_activity_id else "none"
        return f"{self.activity_definition_count} trusted activities | active {active}"

    @property
    def privacy_summary(self) -> str:
        if self.privacy.local_only:
            return "Local only | no payments, telemetry, uploads, or marketplace"
        return "Unexpected remote capability enabled"


@dataclass(frozen=True, slots=True)
class PetStatusSnapshot:
    """One coherent read-only answer to how Akiha is doing."""

    pet: PetDiagnosticsSnapshot
    runtime: PetRuntimeStatus
    systems: PetSystemDiagnostics

    def __post_init__(self) -> None:
        if not isinstance(self.pet, PetDiagnosticsSnapshot):
            raise TypeError("pet must be a PetDiagnosticsSnapshot value.")
        if not isinstance(self.runtime, PetRuntimeStatus):
            raise TypeError("runtime must be a PetRuntimeStatus value.")
        if not isinstance(self.systems, PetSystemDiagnostics):
            raise TypeError("systems must be a PetSystemDiagnostics value.")

    @property
    def headline(self) -> str:
        minimum = min(
            self.pet.satiety,
            self.pet.energy,
            self.pet.attention,
            self.pet.affection,
        )
        if minimum <= 25:
            return "Akiha needs care"
        if minimum <= 50:
            return "Akiha could use some attention"
        return "Akiha is doing well"


class PetStatusService:
    """Aggregate existing typed state without adding a mutation surface."""

    def __init__(
        self,
        pet_state_service: PetSnapshotService,
        catalog_result: CatalogLoadResult,
        shop_repository: ShopRepository,
        appearance_service: AppearanceService,
        activity_definitions: tuple[PetActivityDefinition, ...],
    ) -> None:
        if not isinstance(catalog_result, CatalogLoadResult):
            raise TypeError("catalog_result must be a CatalogLoadResult value.")
        if not isinstance(activity_definitions, tuple) or any(
            not isinstance(item, PetActivityDefinition) for item in activity_definitions
        ):
            raise TypeError("activity_definitions must contain typed definitions.")
        self._pet_state_service = pet_state_service
        self._catalog_result = catalog_result
        self._shop_repository = shop_repository
        self._appearance_service = appearance_service
        self._activity_definitions = activity_definitions

    async def snapshot(self, runtime: PetRuntimeStatus) -> PetStatusSnapshot:
        """Read local subsystem state and return sanitized aggregate status."""
        if not isinstance(runtime, PetRuntimeStatus):
            raise TypeError("runtime must be a PetRuntimeStatus value.")
        record, inventory, transaction_count, latest, appearances = (
            await asyncio.gather(
                self._pet_state_service.snapshot(),
                self._shop_repository.list_inventory(),
                self._shop_repository.count_transactions(),
                self._shop_repository.list_transactions(1),
                self._appearance_service.list_appearances(),
            )
        )
        return PetStatusSnapshot(
            pet=build_pet_diagnostics(record),
            runtime=runtime,
            systems=self._build_system_diagnostics(
                inventory_count=len(inventory),
                transaction_count=transaction_count,
                latest_purchase_at=(latest[0].purchased_at if latest else None),
                appearances=appearances,
                active_activity_id=runtime.autonomous_activity_id,
            ),
        )

    def _build_system_diagnostics(
        self,
        *,
        inventory_count: int,
        transaction_count: int,
        latest_purchase_at: datetime | None,
        appearances: tuple[AppearanceView, ...],
        active_activity_id: PetActivityId | None,
    ) -> PetSystemDiagnostics:
        catalog = self._catalog_result.catalog
        return PetSystemDiagnostics(
            catalog_version=catalog.version,
            catalog_item_count=len(catalog.items),
            available_catalog_item_count=sum(
                item.availability is CatalogAvailability.AVAILABLE
                for item in catalog.items
            ),
            catalog_failure=(
                self._catalog_result.failure.value
                if self._catalog_result.failure is not None
                else None
            ),
            owned_item_count=inventory_count,
            transaction_count=transaction_count,
            last_purchase_at=latest_purchase_at,
            appearance_count=len(appearances),
            available_appearance_count=sum(
                view.availability is AppearanceAvailability.AVAILABLE
                for view in appearances
            ),
            owned_appearance_count=sum(view.owned for view in appearances),
            current_appearance_id=self._appearance_service.current_appearance_id,
            activity_definition_count=len(self._activity_definitions),
            active_activity_id=active_activity_id,
        )
