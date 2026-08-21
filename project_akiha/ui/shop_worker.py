"""Qt worker for typed shop and complete-appearance operations."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum

from PySide6.QtCore import QObject, QThread, Signal

from project_akiha.core.appearance import (
    AppearanceId,
    AppearanceSelectionOutcome,
    AppearanceView,
)
from project_akiha.core.shop import (
    CatalogQuery,
    ShopBrowseResult,
    ShopInventoryItemView,
    ShopPurchaseResult,
)
from project_akiha.services.appearance import AppearanceService
from project_akiha.services.shop import ShopService


class ShopWorkerOperation(StrEnum):
    """Closed UI operations accepted by the shop worker."""

    REFRESH = "refresh"
    PURCHASE = "purchase"
    SELECT_APPEARANCE = "select_appearance"


@dataclass(frozen=True, slots=True)
class ShopUiSnapshot:
    """One internally consistent sanitized presentation snapshot."""

    browse: ShopBrowseResult
    inventory: tuple[ShopInventoryItemView, ...]
    appearances: tuple[AppearanceView, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.browse, ShopBrowseResult):
            raise TypeError("browse must be a ShopBrowseResult value.")
        if not isinstance(self.inventory, tuple) or any(
            not isinstance(item, ShopInventoryItemView) for item in self.inventory
        ):
            raise TypeError("inventory must contain ShopInventoryItemView values.")
        if not isinstance(self.appearances, tuple) or any(
            not isinstance(item, AppearanceView) for item in self.appearances
        ):
            raise TypeError("appearances must contain AppearanceView values.")


@dataclass(frozen=True, slots=True)
class ShopWorkerResult:
    """One operation outcome paired with the resulting visible state."""

    operation: ShopWorkerOperation
    snapshot: ShopUiSnapshot
    purchase: ShopPurchaseResult | None = None
    appearance: AppearanceSelectionOutcome | None = None

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
        if self.operation is ShopWorkerOperation.SELECT_APPEARANCE:
            if not isinstance(self.appearance, AppearanceSelectionOutcome):
                raise ValueError("appearance operations require a selection result.")
        elif self.appearance is not None:
            raise ValueError(
                "non-appearance operations cannot contain appearance data."
            )


class ShopOperationThread(QThread):
    """Run one bounded shop operation away from the Qt UI thread."""

    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        shop_service: ShopService,
        appearance_service: AppearanceService,
        operation: ShopWorkerOperation,
        *,
        query: CatalogQuery | None = None,
        item_id: str | None = None,
        appearance_id: AppearanceId | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if not isinstance(operation, ShopWorkerOperation):
            raise TypeError("operation must be a ShopWorkerOperation value.")
        if query is not None and not isinstance(query, CatalogQuery):
            raise TypeError("query must be a CatalogQuery value or None.")
        if item_id is not None and (not isinstance(item_id, str) or not item_id):
            raise ValueError("item_id must be a nonempty string or None.")
        if appearance_id is not None and not isinstance(appearance_id, AppearanceId):
            raise TypeError("appearance_id must be an AppearanceId value or None.")
        _validate_arguments(operation, item_id, appearance_id)
        self._shop_service = shop_service
        self._appearance_service = appearance_service
        self._operation = operation
        self._query = query
        self._item_id = item_id
        self._appearance_id = appearance_id

    def run(self) -> None:
        try:
            self.completed.emit(asyncio.run(self._execute()))
        except Exception as error:
            self.failed.emit(str(error))

    async def _execute(self) -> ShopWorkerResult:
        purchase: ShopPurchaseResult | None = None
        appearance: AppearanceSelectionOutcome | None = None
        if self._operation is ShopWorkerOperation.PURCHASE:
            purchase = await self._shop_service.purchase(
                _require_item_id(self._item_id)
            )
        elif self._operation is ShopWorkerOperation.SELECT_APPEARANCE:
            appearance = await self._appearance_service.select(
                _require_appearance_id(self._appearance_id)
            )
        snapshot = ShopUiSnapshot(
            browse=await self._shop_service.browse(self._query),
            inventory=await self._shop_service.inventory(),
            appearances=await self._appearance_service.list_appearances(),
        )
        return ShopWorkerResult(
            operation=self._operation,
            snapshot=snapshot,
            purchase=purchase,
            appearance=appearance,
        )

    def cancel(self) -> None:
        self.requestInterruption()


def _validate_arguments(
    operation: ShopWorkerOperation,
    item_id: str | None,
    appearance_id: AppearanceId | None,
) -> None:
    if operation is ShopWorkerOperation.PURCHASE:
        if item_id is None or appearance_id is not None:
            raise ValueError("purchase requires only an item ID.")
    elif operation is ShopWorkerOperation.SELECT_APPEARANCE:
        if appearance_id is None or item_id is not None:
            raise ValueError("appearance selection requires only an appearance ID.")
    elif item_id is not None or appearance_id is not None:
        raise ValueError("refresh cannot contain mutation arguments.")


def _require_item_id(value: str | None) -> str:
    if value is None:
        raise RuntimeError("The typed shop operation is missing its item ID.")
    return value


def _require_appearance_id(value: AppearanceId | None) -> AppearanceId:
    if value is None:
        raise RuntimeError("The typed operation is missing its appearance ID.")
    return value
