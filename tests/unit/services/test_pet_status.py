"""Tests for aggregate read-only Phase 10 status."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from uuid import UUID

from project_akiha.core.appearance import (
    AppearanceAvailability,
    AppearanceId,
    AppearanceView,
)
from project_akiha.core.behavior import ActivityState, CompanionMood
from project_akiha.core.pet import PetState, PetStateRecord
from project_akiha.core.pet_activity import PetActivityId
from project_akiha.core.shop import (
    CatalogLoadResult,
    PurchaseTransaction,
    ShopCatalog,
)
from project_akiha.core.state.animation import AnimationState
from project_akiha.services.pet_status import (
    PHASE10_PRIVACY_BOUNDARY,
    PetRuntimeStatus,
    PetStatusService,
)


class PetStatusServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_aggregates_only_typed_local_status_and_diagnostics(self) -> None:
        now = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
        service = PetStatusService(
            _PetStateService(now),
            CatalogLoadResult(ShopCatalog.empty(version=2)),
            _ShopRepository(now),  # type: ignore[arg-type]
            _AppearanceService(),  # type: ignore[arg-type]
            (),
        )

        snapshot = await service.snapshot(
            PetRuntimeStatus(
                mood=CompanionMood.CALM,
                user_activity=ActivityState.IDLE,
                animation_state=AnimationState.IDLE,
                autonomous_activity_id=PetActivityId.QUIET_IDLE,
            )
        )

        self.assertEqual(snapshot.headline, "Akiha could use some attention")
        self.assertEqual(snapshot.systems.catalog_version, 2)
        self.assertEqual(snapshot.systems.owned_item_count, 1)
        self.assertEqual(snapshot.systems.transaction_count, 1)
        self.assertEqual(snapshot.systems.current_appearance_id, AppearanceId.SEIFUKU)
        self.assertTrue(snapshot.systems.privacy.local_only)
        self.assertNotIn("credential", snapshot.systems.privacy_summary.casefold())

    def test_phase10_privacy_boundary_disables_remote_store_capabilities(self) -> None:
        self.assertFalse(PHASE10_PRIVACY_BOUNDARY.real_money_store)
        self.assertFalse(PHASE10_PRIVACY_BOUNDARY.telemetry)
        self.assertFalse(PHASE10_PRIVACY_BOUNDARY.cloud_asset_upload)
        self.assertFalse(PHASE10_PRIVACY_BOUNDARY.remote_marketplace)
        self.assertTrue(PHASE10_PRIVACY_BOUNDARY.local_only)


class _PetStateService:
    def __init__(self, now: datetime) -> None:
        self._record = PetStateRecord(
            state=PetState.initial(),
            revision=0,
            evaluated_at=now,
            created_at=now,
            updated_at=now,
        )

    async def snapshot(self) -> PetStateRecord:
        return self._record


class _ShopRepository:
    def __init__(self, now: datetime) -> None:
        self._transaction = PurchaseTransaction(
            transaction_id=UUID("00000000-0000-0000-0000-000000000001"),
            item_id="appearance.dress",
            catalog_version=2,
            price=0,
            balance_before=0,
            balance_after=0,
            purchased_at=now,
        )

    async def list_inventory(self) -> tuple[object, ...]:
        return (object(),)

    async def count_transactions(self) -> int:
        return 1

    async def list_transactions(self, limit: int) -> tuple[PurchaseTransaction, ...]:
        self.assert_limit = limit
        return (self._transaction,)


class _AppearanceService:
    current_appearance_id = AppearanceId.SEIFUKU

    async def list_appearances(self) -> tuple[AppearanceView, ...]:
        return (
            AppearanceView(
                appearance_id=AppearanceId.SEIFUKU,
                display_name="Akiha - Seifuku",
                availability=AppearanceAvailability.AVAILABLE,
                owned=True,
                selected=True,
            ),
        )


if __name__ == "__main__":
    unittest.main()
