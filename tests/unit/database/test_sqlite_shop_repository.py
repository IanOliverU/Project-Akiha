"""Tests for durable ownership and atomic shop purchases."""

from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from project_akiha.core.appearance import AppearanceId
from project_akiha.core.pet import PetProgression, PetState
from project_akiha.core.shop import (
    CatalogAvailability,
    CatalogItem,
    PurchaseDecision,
    ShopIdempotencyConflictError,
    ShopItemCategory,
    ShopStateUnavailableError,
)
from project_akiha.database import SQLitePetStateRepository, SQLiteShopRepository


def _item(
    item_id: str = "appearance.dress",
    *,
    appearance_id: AppearanceId = AppearanceId.DRESS,
    price: int = 20,
    availability: CatalogAvailability = CatalogAvailability.AVAILABLE,
    required_level: int = 1,
) -> CatalogItem:
    return CatalogItem(
        item_id=item_id,
        display_name=item_id.replace(".", " ").title(),
        category=ShopItemCategory.APPEARANCE,
        appearance_id=appearance_id,
        price=price,
        availability=availability,
        required_level=required_level,
        catalog_version=1,
    )


class SQLiteShopRepositoryTest(unittest.IsolatedAsyncioTestCase):
    """Verify restart-safe records and the all-or-nothing economy boundary."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self._database_path = Path(self._temporary_directory.name) / "akiha.sqlite3"
        self._started_at = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
        self._pet_repository = SQLitePetStateRepository(self._database_path)
        await self._pet_repository.load_or_create(
            PetState(progression=PetProgression(currency=100)),
            self._started_at,
        )
        self._repository = SQLiteShopRepository(self._database_path)

    async def test_purchase_atomically_debits_currency_and_grants_inventory(
        self,
    ) -> None:
        transaction_id = uuid4()
        outcome = await self._repository.purchase(
            _item(),
            transaction_id=transaction_id,
            purchased_at=self._started_at + timedelta(minutes=1),
        )

        pet_record = await self._pet_repository.load()
        inventory = await self._repository.list_inventory()
        transaction = await self._repository.get_transaction(transaction_id)

        self.assertIs(outcome.decision, PurchaseDecision.COMPLETED)
        self.assertEqual((outcome.balance_before, outcome.balance_after), (100, 80))
        self.assertIsNotNone(pet_record)
        assert pet_record is not None
        self.assertEqual(pet_record.state.progression.currency, 80)
        self.assertEqual(pet_record.state.progression.xp, 0)
        self.assertEqual(pet_record.revision, 1)
        self.assertEqual(inventory, (outcome.inventory_item,))
        self.assertEqual(transaction, outcome.transaction)

    async def test_same_transaction_replays_without_a_second_charge(self) -> None:
        transaction_id = uuid4()
        purchased_at = self._started_at + timedelta(minutes=1)

        first = await self._repository.purchase(
            _item(),
            transaction_id=transaction_id,
            purchased_at=purchased_at,
        )
        replay = await self._repository.purchase(
            _item(),
            transaction_id=transaction_id,
            purchased_at=purchased_at + timedelta(minutes=5),
        )

        pet_record = await self._pet_repository.load()
        self.assertEqual(replay, first)
        self.assertIsNotNone(pet_record)
        assert pet_record is not None
        self.assertEqual(pet_record.state.progression.currency, 80)
        self.assertEqual(len(await self._repository.list_transactions(10)), 1)
        self.assertEqual(len(await self._repository.list_inventory()), 1)

    async def test_second_transaction_for_owned_item_is_denied_without_charge(
        self,
    ) -> None:
        await self._repository.purchase(
            _item(),
            transaction_id=uuid4(),
            purchased_at=self._started_at,
        )

        duplicate = await self._repository.purchase(
            _item(),
            transaction_id=uuid4(),
            purchased_at=self._started_at + timedelta(minutes=1),
        )

        self.assertIs(duplicate.decision, PurchaseDecision.ALREADY_OWNED)
        self.assertEqual((duplicate.balance_before, duplicate.balance_after), (80, 80))
        self.assertEqual(len(await self._repository.list_transactions(10)), 1)

    async def test_transaction_id_cannot_be_reused_for_another_item(self) -> None:
        transaction_id = uuid4()
        await self._repository.purchase(
            _item(),
            transaction_id=transaction_id,
            purchased_at=self._started_at,
        )

        with self.assertRaises(ShopIdempotencyConflictError):
            await self._repository.purchase(
                _item("appearance.vermillion", appearance_id=AppearanceId.VERMILLION),
                transaction_id=transaction_id,
                purchased_at=self._started_at + timedelta(minutes=1),
            )

        pet_record = await self._pet_repository.load()
        self.assertIsNotNone(pet_record)
        assert pet_record is not None
        self.assertEqual(pet_record.state.progression.currency, 80)
        self.assertEqual(len(await self._repository.list_inventory()), 1)

    async def test_purchase_denials_preserve_currency_and_create_no_records(
        self,
    ) -> None:
        cases = (
            (
                _item(
                    "appearance.hidden",
                    appearance_id=AppearanceId.VERMILLION,
                    availability=CatalogAvailability.HIDDEN,
                ),
                PurchaseDecision.ITEM_UNAVAILABLE,
            ),
            (
                _item(
                    "appearance.level",
                    appearance_id=AppearanceId.VERMILLION,
                    required_level=2,
                ),
                PurchaseDecision.LEVEL_REQUIRED,
            ),
            (
                _item(
                    "appearance.costly",
                    appearance_id=AppearanceId.VERMILLION,
                    price=101,
                ),
                PurchaseDecision.INSUFFICIENT_FUNDS,
            ),
        )

        for item, decision in cases:
            with self.subTest(decision=decision):
                outcome = await self._repository.purchase(
                    item,
                    transaction_id=uuid4(),
                    purchased_at=self._started_at,
                )
                self.assertIs(outcome.decision, decision)
                self.assertEqual(
                    (outcome.balance_before, outcome.balance_after),
                    (100, 100),
                )

        pet_record = await self._pet_repository.load()
        self.assertIsNotNone(pet_record)
        assert pet_record is not None
        self.assertEqual(pet_record.state.progression.currency, 100)
        self.assertEqual(await self._repository.list_inventory(), ())
        self.assertEqual(await self._repository.list_transactions(10), ())

    async def test_inventory_failure_rolls_back_currency_and_transaction(self) -> None:
        connection = sqlite3.connect(self._database_path)
        try:
            connection.execute("""
                CREATE TRIGGER fail_shop_inventory_insert
                BEFORE INSERT ON shop_inventory
                BEGIN
                    SELECT RAISE(ABORT, 'forced inventory failure');
                END
                """)
            connection.commit()
        finally:
            connection.close()
        transaction_id = uuid4()

        with self.assertRaises(sqlite3.IntegrityError):
            await self._repository.purchase(
                _item(),
                transaction_id=transaction_id,
                purchased_at=self._started_at,
            )

        pet_record = await self._pet_repository.load()
        self.assertIsNotNone(pet_record)
        assert pet_record is not None
        self.assertEqual(pet_record.state.progression.currency, 100)
        self.assertEqual(pet_record.revision, 0)
        self.assertIsNone(await self._repository.get_transaction(transaction_id))
        self.assertEqual(await self._repository.list_inventory(), ())

    async def test_concurrent_duplicate_purchase_charges_once(self) -> None:
        outcomes = await asyncio.gather(
            self._repository.purchase(
                _item(),
                transaction_id=uuid4(),
                purchased_at=self._started_at,
            ),
            self._repository.purchase(
                _item(),
                transaction_id=uuid4(),
                purchased_at=self._started_at,
            ),
        )

        decisions = {outcome.decision for outcome in outcomes}
        self.assertEqual(
            decisions,
            {PurchaseDecision.COMPLETED, PurchaseDecision.ALREADY_OWNED},
        )
        pet_record = await self._pet_repository.load()
        self.assertIsNotNone(pet_record)
        assert pet_record is not None
        self.assertEqual(pet_record.state.progression.currency, 80)

    async def test_purchase_requires_initialized_pet_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = SQLiteShopRepository(Path(directory) / "akiha.sqlite3")
            with self.assertRaises(ShopStateUnavailableError):
                await repository.purchase(
                    _item(),
                    transaction_id=uuid4(),
                    purchased_at=self._started_at,
                )

    async def test_argument_validation_rejects_untyped_inputs(self) -> None:
        with self.assertRaises(TypeError):
            await self._repository.purchase(  # type: ignore[arg-type]
                "appearance.dress",
                transaction_id=uuid4(),
                purchased_at=self._started_at,
            )
        with self.assertRaises(ValueError):
            await self._repository.purchase(
                _item(),
                transaction_id=uuid4(),
                purchased_at=datetime(2026, 8, 21, 12, 0),
            )
        with self.assertRaises(TypeError):
            await self._repository.list_transactions(True)


if __name__ == "__main__":
    unittest.main()
