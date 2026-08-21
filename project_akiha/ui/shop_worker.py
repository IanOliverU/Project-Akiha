"""Qt worker for typed shop, inventory, and wardrobe operations."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum

from PySide6.QtCore import QObject, QThread, Signal

from project_akiha.core.shop import (
    CatalogQuery,
    EquipmentOutcome,
    EquipmentSlot,
    ShopBrowseResult,
    ShopInventoryItemView,
    ShopLoadoutView,
    ShopPurchaseResult,
)
from project_akiha.services.shop import ShopService


class ShopWorkerOperation(StrEnum):
    """Closed UI operations accepted by the shop worker."""

    REFRESH = "refresh"
    PURCHASE = "purchase"
    EQUIP = "equip"
    UNEQUIP = "unequip"


@dataclass(frozen=True, slots=True)
class ShopUiSnapshot:
    """One internally consistent sanitized presentation snapshot."""

    browse: ShopBrowseResult
    inventory: tuple[ShopInventoryItemView, ...]
    loadout: ShopLoadoutView

    def __post_init__(self) -> None:
        if not isinstance(self.browse, ShopBrowseResult):
            raise TypeError("browse must be a ShopBrowseResult value.")
        if not isinstance(self.inventory, tuple) or any(
            not isinstance(item, ShopInventoryItemView) for item in self.inventory
        ):
            raise TypeError("inventory must contain ShopInventoryItemView values.")
        if not isinstance(self.loadout, ShopLoadoutView):
            raise TypeError("loadout must be a ShopLoadoutView value.")


@dataclass(frozen=True, slots=True)
class ShopWorkerResult:
    """One operation outcome paired with the resulting visible state."""

    operation: ShopWorkerOperation
    snapshot: ShopUiSnapshot
    purchase: ShopPurchaseResult | None = None
    equipment: EquipmentOutcome | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.operation, ShopWorkerOperation):
            raise TypeError("operation must be a ShopWorkerOperation value.")
        if not isinstance(self.snapshot, ShopUiSnapshot):
            raise TypeError("snapshot must be a ShopUiSnapshot value.")
        if self.operation is ShopWorkerOperation.PURCHASE:
            if not isinstance(self.purchase, ShopPurchaseResult):
                raise ValueError("purchase operations require a purchase result.")
        elif self.purchase is not None:
            raise ValueError("non-purchase operations cannot contain purchase data.")
        if self.operation in {
            ShopWorkerOperation.EQUIP,
            ShopWorkerOperation.UNEQUIP,
        }:
            if not isinstance(self.equipment, EquipmentOutcome):
                raise ValueError("equipment operations require an equipment result.")
        elif self.equipment is not None:
            raise ValueError("non-equipment operations cannot contain equipment data.")


class ShopOperationThread(QThread):
    """Run one bounded shop operation away from the Qt UI thread."""

    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        service: ShopService,
        operation: ShopWorkerOperation,
        *,
        query: CatalogQuery | None = None,
        item_id: str | None = None,
        slot: EquipmentSlot | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if not isinstance(operation, ShopWorkerOperation):
            raise TypeError("operation must be a ShopWorkerOperation value.")
        if query is not None and not isinstance(query, CatalogQuery):
            raise TypeError("query must be a CatalogQuery value or None.")
        if item_id is not None and (not isinstance(item_id, str) or not item_id):
            raise ValueError("item_id must be a nonempty string or None.")
        if slot is not None and not isinstance(slot, EquipmentSlot):
            raise TypeError("slot must be an EquipmentSlot value or None.")
        _validate_operation_arguments(operation, item_id=item_id, slot=slot)
        self._service = service
        self._operation = operation
        self._query = query
        self._item_id = item_id
        self._slot = slot

    def run(self) -> None:
        """Execute the typed operation and return a complete refreshed snapshot."""
        try:
            self.completed.emit(asyncio.run(self._execute()))
        except Exception as error:
            self.failed.emit(str(error))

    async def _execute(self) -> ShopWorkerResult:
        purchase: ShopPurchaseResult | None = None
        equipment: EquipmentOutcome | None = None
        if self._operation is ShopWorkerOperation.PURCHASE:
            purchase = await self._service.purchase(_require_item_id(self._item_id))
        elif self._operation is ShopWorkerOperation.EQUIP:
            equipment = await self._service.equip(_require_item_id(self._item_id))
        elif self._operation is ShopWorkerOperation.UNEQUIP:
            equipment = await self._service.unequip(_require_slot(self._slot))

        snapshot = ShopUiSnapshot(
            browse=await self._service.browse(self._query),
            inventory=await self._service.inventory(),
            loadout=await self._service.loadout(),
        )
        return ShopWorkerResult(
            operation=self._operation,
            snapshot=snapshot,
            purchase=purchase,
            equipment=equipment,
        )

    def cancel(self) -> None:
        """Mark the short operation for shutdown coordination."""
        self.requestInterruption()


def _validate_operation_arguments(
    operation: ShopWorkerOperation,
    *,
    item_id: str | None,
    slot: EquipmentSlot | None,
) -> None:
    if operation in {ShopWorkerOperation.PURCHASE, ShopWorkerOperation.EQUIP}:
        if item_id is None or slot is not None:
            raise ValueError(f"{operation.value} requires only an item ID.")
        return
    if operation is ShopWorkerOperation.UNEQUIP:
        if slot is None or item_id is not None:
            raise ValueError("unequip requires only an equipment slot.")
        return
    if item_id is not None or slot is not None:
        raise ValueError("refresh cannot contain mutation arguments.")


def _require_item_id(item_id: str | None) -> str:
    if item_id is None:
        raise RuntimeError("The typed shop operation is missing its item ID.")
    return item_id


def _require_slot(slot: EquipmentSlot | None) -> EquipmentSlot:
    if slot is None:
        raise RuntimeError("The typed shop operation is missing its slot.")
    return slot
