"""SQLite persistence and atomic currency transactions for the local shop."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from project_akiha.core.shop import (
    AcquisitionSource,
    CatalogAvailability,
    CatalogItem,
    InventoryItem,
    PurchaseDecision,
    PurchaseOutcome,
    PurchaseTransaction,
    ShopIdempotencyConflictError,
    ShopStateUnavailableError,
)
from project_akiha.database.migrator import DatabaseMigrator


class SQLiteShopRepository:
    """Persist shop state and own the cross-table purchase transaction."""

    def __init__(self, database_path: Path) -> None:
        if not isinstance(database_path, Path):
            raise TypeError("database_path must be a Path value.")
        self._database_path = database_path
        DatabaseMigrator(database_path).apply_pending()

    async def get_inventory_item(self, item_id: str) -> InventoryItem | None:
        """Return one durable ownership record when present."""
        _require_nonempty_string(item_id, "item_id")
        return await asyncio.to_thread(self._get_inventory_item, item_id)

    async def list_inventory(self) -> tuple[InventoryItem, ...]:
        """Return all owned items in stable acquisition order."""
        return await asyncio.to_thread(self._list_inventory)

    async def get_transaction(
        self,
        transaction_id: UUID,
    ) -> PurchaseTransaction | None:
        """Return one completed purchase transaction when present."""
        if not isinstance(transaction_id, UUID):
            raise TypeError("transaction_id must be a UUID.")
        return await asyncio.to_thread(self._get_transaction, transaction_id)

    async def list_transactions(self, limit: int) -> tuple[PurchaseTransaction, ...]:
        """Return recent completed purchases newest first."""
        if type(limit) is not int:
            raise TypeError("transaction limit must be an integer.")
        if limit <= 0:
            raise ValueError("transaction limit must be greater than zero.")
        return await asyncio.to_thread(self._list_transactions, limit)

    async def purchase(
        self,
        item: CatalogItem,
        *,
        transaction_id: UUID,
        purchased_at: datetime,
    ) -> PurchaseOutcome:
        """Atomically debit pet currency and grant non-stackable ownership."""
        if not isinstance(item, CatalogItem):
            raise TypeError("item must be a CatalogItem value.")
        if not isinstance(transaction_id, UUID):
            raise TypeError("transaction_id must be a UUID.")
        normalized_time = _normalize_datetime(purchased_at, "purchased_at")
        return await asyncio.to_thread(
            self._purchase,
            item,
            transaction_id,
            normalized_time,
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _get_inventory_item(self, item_id: str) -> InventoryItem | None:
        connection = self._connect()
        try:
            row = _select_inventory_item(connection, item_id)
        finally:
            connection.close()
        return _inventory_from_row(row) if row is not None else None

    def _list_inventory(self) -> tuple[InventoryItem, ...]:
        connection = self._connect()
        try:
            rows = connection.execute("""
                SELECT item_id,
                       acquired_at,
                       acquisition_source,
                       purchase_transaction_id
                FROM shop_inventory
                ORDER BY acquired_at ASC, item_id ASC
                """).fetchall()
        finally:
            connection.close()
        return tuple(_inventory_from_row(row) for row in rows)

    def _get_transaction(
        self,
        transaction_id: UUID,
    ) -> PurchaseTransaction | None:
        connection = self._connect()
        try:
            row = _select_transaction(connection, transaction_id)
        finally:
            connection.close()
        return _transaction_from_row(row) if row is not None else None

    def _list_transactions(self, limit: int) -> tuple[PurchaseTransaction, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT transaction_id,
                       item_id,
                       catalog_version,
                       price,
                       balance_before,
                       balance_after,
                       purchased_at
                FROM shop_transactions
                ORDER BY purchased_at DESC, transaction_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            connection.close()
        return tuple(_transaction_from_row(row) for row in rows)

    def _purchase(
        self,
        item: CatalogItem,
        transaction_id: UUID,
        purchased_at: datetime,
    ) -> PurchaseOutcome:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing_transaction = _select_transaction(connection, transaction_id)
            if existing_transaction is not None:
                transaction = _transaction_from_row(existing_transaction)
                if transaction.item_id != item.item_id:
                    raise ShopIdempotencyConflictError(
                        "The transaction ID is already assigned to another item."
                    )
                inventory_row = _select_inventory_item(connection, item.item_id)
                if inventory_row is None:
                    raise RuntimeError(
                        "A completed shop transaction is missing its inventory grant."
                    )
                inventory = _inventory_from_row(inventory_row)
                connection.commit()
                return PurchaseOutcome(
                    decision=PurchaseDecision.COMPLETED,
                    balance_before=transaction.balance_before,
                    balance_after=transaction.balance_after,
                    transaction=transaction,
                    inventory_item=inventory,
                )

            state = _select_pet_progression(connection)
            if state is None:
                raise ShopStateUnavailableError(
                    "Pet progression must be initialized before purchasing."
                )
            balance = int(state["currency"])
            if _select_inventory_item(connection, item.item_id) is not None:
                connection.commit()
                return _denied_outcome(PurchaseDecision.ALREADY_OWNED, balance)
            if item.availability is not CatalogAvailability.AVAILABLE:
                connection.commit()
                return _denied_outcome(PurchaseDecision.ITEM_UNAVAILABLE, balance)
            if int(state["level"]) < item.required_level:
                connection.commit()
                return _denied_outcome(PurchaseDecision.LEVEL_REQUIRED, balance)
            if balance < item.price:
                connection.commit()
                return _denied_outcome(PurchaseDecision.INSUFFICIENT_FUNDS, balance)

            timestamp = _timestamp(purchased_at)
            next_balance = balance - item.price
            revision = int(state["revision"])
            cursor = connection.execute(
                """
                UPDATE pet_state
                SET currency = ?,
                    revision = ?,
                    updated_at = ?
                WHERE id = 1 AND revision = ? AND currency = ?
                """,
                (next_balance, revision + 1, timestamp, revision, balance),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Pet currency changed before the purchase commit.")
            connection.execute(
                """
                INSERT INTO shop_transactions(
                    transaction_id,
                    item_id,
                    catalog_version,
                    price,
                    balance_before,
                    balance_after,
                    purchased_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(transaction_id),
                    item.item_id,
                    item.catalog_version,
                    item.price,
                    balance,
                    next_balance,
                    timestamp,
                ),
            )
            connection.execute(
                """
                INSERT INTO shop_inventory(
                    item_id,
                    acquired_at,
                    acquisition_source,
                    purchase_transaction_id
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    item.item_id,
                    timestamp,
                    AcquisitionSource.PURCHASE.value,
                    str(transaction_id),
                ),
            )
            transaction = PurchaseTransaction(
                transaction_id=transaction_id,
                item_id=item.item_id,
                catalog_version=item.catalog_version,
                price=item.price,
                balance_before=balance,
                balance_after=next_balance,
                purchased_at=purchased_at,
            )
            inventory = InventoryItem(
                item_id=item.item_id,
                acquired_at=purchased_at,
                acquisition_source=AcquisitionSource.PURCHASE,
                purchase_transaction_id=transaction_id,
            )
            connection.commit()
            return PurchaseOutcome(
                decision=PurchaseDecision.COMPLETED,
                balance_before=balance,
                balance_after=next_balance,
                transaction=transaction,
                inventory_item=inventory,
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def _select_pet_progression(connection: sqlite3.Connection) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT level, currency, revision FROM pet_state WHERE id = 1"
    ).fetchone()


def _select_inventory_item(
    connection: sqlite3.Connection,
    item_id: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT item_id,
               acquired_at,
               acquisition_source,
               purchase_transaction_id
        FROM shop_inventory
        WHERE item_id = ?
        """,
        (item_id,),
    ).fetchone()


def _select_transaction(
    connection: sqlite3.Connection,
    transaction_id: UUID,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT transaction_id,
               item_id,
               catalog_version,
               price,
               balance_before,
               balance_after,
               purchased_at
        FROM shop_transactions
        WHERE transaction_id = ?
        """,
        (str(transaction_id),),
    ).fetchone()


def _inventory_from_row(row: sqlite3.Row) -> InventoryItem:
    transaction_id = row["purchase_transaction_id"]
    return InventoryItem(
        item_id=str(row["item_id"]),
        acquired_at=_datetime_from_text(row["acquired_at"]),
        acquisition_source=AcquisitionSource(str(row["acquisition_source"])),
        purchase_transaction_id=(
            UUID(str(transaction_id)) if transaction_id is not None else None
        ),
    )


def _transaction_from_row(row: sqlite3.Row) -> PurchaseTransaction:
    return PurchaseTransaction(
        transaction_id=UUID(str(row["transaction_id"])),
        item_id=str(row["item_id"]),
        catalog_version=int(row["catalog_version"]),
        price=int(row["price"]),
        balance_before=int(row["balance_before"]),
        balance_after=int(row["balance_after"]),
        purchased_at=_datetime_from_text(row["purchased_at"]),
    )


def _denied_outcome(decision: PurchaseDecision, balance: int) -> PurchaseOutcome:
    return PurchaseOutcome(
        decision=decision,
        balance_before=balance,
        balance_after=balance,
    )


def _require_nonempty_string(value: object, label: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string.")
    if not value:
        raise ValueError(f"{label} cannot be empty.")


def _normalize_datetime(value: object, label: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{label} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware.")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _datetime_from_text(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Persisted shop timestamps must be timezone-aware.")
    return parsed.astimezone(UTC)
