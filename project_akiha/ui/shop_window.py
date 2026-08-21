"""Compact trusted shop and wardrobe surface for Akiha."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from project_akiha.core.shop import (
    CatalogAvailability,
    CatalogOwnershipFilter,
    CatalogQuery,
    CatalogSort,
    EquipmentDecision,
    EquipmentSlot,
    PurchaseDecision,
    ShopInventoryItemView,
    ShopItemCategory,
    ShopItemView,
)
from project_akiha.ui.fluent_icons import FluentComboBox, fluent_icon
from project_akiha.ui.shop_worker import ShopUiSnapshot, ShopWorkerResult
from project_akiha.ui.theme import shop_window_stylesheet

_SHOP_ITEM_ROLE = Qt.ItemDataRole.UserRole
_INVENTORY_ITEM_ROLE = Qt.ItemDataRole.UserRole


class ShopWindow(QWidget):
    """Present trusted catalog and wardrobe state with explicit mutations."""

    refresh_requested = Signal(object)
    purchase_requested = Signal(str)
    equip_requested = Signal(str)
    unequip_requested = Signal(object)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        purchase_confirmation: Callable[[ShopItemView], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Akiha Shop")
        self.setObjectName("akihaShopWindow")
        self.setMinimumSize(760, 540)
        self.resize(900, 620)
        self.setStyleSheet(shop_window_stylesheet())
        self._purchase_confirmation = purchase_confirmation or self._confirm_purchase
        self._snapshot: ShopUiSnapshot | None = None
        self._shop_items: dict[str, ShopItemView] = {}
        self._inventory_items: dict[str, ShopInventoryItemView] = {}
        self._loadout_labels: dict[EquipmentSlot, QLabel] = {}
        self._unequip_buttons: dict[EquipmentSlot, QPushButton] = {}

        header = self._build_header()
        self._tabs = QTabWidget()
        self._tabs.setObjectName("shopTabs")
        self._tabs.setDocumentMode(True)
        self._tabs.addTab(self._build_shop_page(), "Shop")
        self._tabs.addTab(self._build_wardrobe_page(), "Wardrobe")

        self._notice_label = QLabel("Loading the trusted local catalog...")
        self._notice_label.setObjectName("shopNotice")
        self._notice_label.setWordWrap(True)

        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(18, 10, 18, 10)
        footer_layout.addWidget(self._notice_label, 1)
        footer = QFrame()
        footer.setObjectName("shopFooter")
        footer.setLayout(footer_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(self._tabs, 1)
        layout.addWidget(footer)
        self.setLayout(layout)

    def _build_header(self) -> QFrame:
        icon = QLabel()
        icon.setPixmap(fluent_icon("\ue719", 20).pixmap(22, 22))
        title = QLabel("Akiha Shop")
        title.setObjectName("shopTitle")
        self._summary_label = QLabel("Level --  |  -- currency")
        self._summary_label.setObjectName("shopSummary")

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(9)
        title_row.addWidget(icon)
        title_row.addWidget(title)

        heading = QVBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(5)
        heading.addLayout(title_row)
        heading.addWidget(self._summary_label)

        self._refresh_button = QPushButton()
        self._refresh_button.setObjectName("shopIconButton")
        self._refresh_button.setIcon(fluent_icon("\ue72c"))
        self._refresh_button.setToolTip("Refresh shop and wardrobe")
        self._refresh_button.clicked.connect(self._emit_refresh)

        close_button = QPushButton()
        close_button.setObjectName("shopIconButton")
        close_button.setIcon(fluent_icon("\ue8bb"))
        close_button.setToolTip("Close")
        close_button.clicked.connect(self.close)

        layout = QHBoxLayout()
        layout.setContentsMargins(20, 16, 14, 16)
        layout.setSpacing(8)
        layout.addLayout(heading)
        layout.addStretch(1)
        layout.addWidget(self._refresh_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(close_button, 0, Qt.AlignmentFlag.AlignTop)
        frame = QFrame()
        frame.setObjectName("shopHeader")
        frame.setLayout(layout)
        return frame

    def _build_shop_page(self) -> QWidget:
        self._search_input = QLineEdit()
        self._search_input.setObjectName("shopSearch")
        self._search_input.setPlaceholderText("Search catalog")
        self._search_input.addAction(
            fluent_icon("\ue721"),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self._search_input.textChanged.connect(self._apply_text_filter)

        self._category_filter = FluentComboBox()
        self._category_filter.setObjectName("shopFilter")
        self._category_filter.setFixedWidth(140)
        self._category_filter.addItem("All categories", None)
        self._category_filter.addItem("Cosmetics", ShopItemCategory.COSMETIC.value)
        self._category_filter.currentIndexChanged.connect(self._emit_refresh)

        self._ownership_filter = FluentComboBox()
        self._ownership_filter.setObjectName("shopFilter")
        self._ownership_filter.setFixedWidth(155)
        self._ownership_filter.addItem(
            "All items",
            CatalogOwnershipFilter.ALL.value,
        )
        self._ownership_filter.addItem(
            "Available to buy",
            CatalogOwnershipFilter.UNOWNED.value,
        )
        self._ownership_filter.addItem(
            "Owned",
            CatalogOwnershipFilter.OWNED.value,
        )
        self._ownership_filter.currentIndexChanged.connect(self._emit_refresh)

        self._sort_filter = FluentComboBox()
        self._sort_filter.setObjectName("shopFilter")
        self._sort_filter.setFixedWidth(170)
        self._sort_filter.addItem("Name", CatalogSort.NAME.value)
        self._sort_filter.addItem(
            "Price: low to high",
            CatalogSort.PRICE_LOW_TO_HIGH.value,
        )
        self._sort_filter.addItem(
            "Price: high to low",
            CatalogSort.PRICE_HIGH_TO_LOW.value,
        )
        self._sort_filter.currentIndexChanged.connect(self._emit_refresh)

        filters = QHBoxLayout()
        filters.setContentsMargins(16, 12, 16, 12)
        filters.setSpacing(8)
        filters.addWidget(self._search_input, 1)
        filters.addWidget(self._category_filter)
        filters.addWidget(self._ownership_filter)
        filters.addWidget(self._sort_filter)
        filter_frame = QFrame()
        filter_frame.setObjectName("shopFilters")
        filter_frame.setLayout(filters)

        self._catalog_list = _build_list("shopCatalogList")
        self._catalog_list.currentItemChanged.connect(self._show_catalog_selection)

        self._item_name_label = QLabel("Select an item")
        self._item_name_label.setObjectName("shopDetailTitle")
        self._item_meta_label = QLabel("Catalog details will appear here.")
        self._item_meta_label.setObjectName("shopDetailMeta")
        self._item_meta_label.setWordWrap(True)
        self._item_price_label = QLabel("-- currency")
        self._item_price_label.setObjectName("shopPrice")
        self._item_status_label = QLabel("No item selected.")
        self._item_status_label.setObjectName("shopItemStatus")
        self._item_status_label.setWordWrap(True)
        self._purchase_button = QPushButton("Purchase")
        self._purchase_button.setObjectName("shopPrimaryButton")
        self._purchase_button.setIcon(fluent_icon("\ue8c7"))
        self._purchase_button.clicked.connect(self._request_purchase_selected)
        self._purchase_button.setEnabled(False)

        detail_layout = QVBoxLayout()
        detail_layout.setContentsMargins(20, 18, 20, 18)
        detail_layout.setSpacing(10)
        detail_layout.addWidget(self._item_name_label)
        detail_layout.addWidget(self._item_meta_label)
        detail_layout.addSpacing(8)
        detail_layout.addWidget(self._item_price_label)
        detail_layout.addWidget(self._item_status_label)
        detail_layout.addStretch(1)
        detail_layout.addWidget(self._purchase_button, 0, Qt.AlignmentFlag.AlignRight)
        detail = QFrame()
        detail.setObjectName("shopDetailPanel")
        detail.setLayout(detail_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("shopSplitter")
        splitter.addWidget(self._catalog_list)
        splitter.addWidget(detail)
        splitter.setSizes([430, 330])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(filter_frame)
        layout.addWidget(splitter, 1)
        page = QWidget()
        page.setObjectName("shopPage")
        page.setLayout(layout)
        return page

    def _build_wardrobe_page(self) -> QWidget:
        self._inventory_list = _build_list("shopInventoryList")
        self._inventory_list.currentItemChanged.connect(self._show_inventory_selection)

        inventory_title = QLabel("Owned items")
        inventory_title.setObjectName("shopSectionTitle")
        inventory_layout = QVBoxLayout()
        inventory_layout.setContentsMargins(16, 14, 10, 14)
        inventory_layout.setSpacing(10)
        inventory_layout.addWidget(inventory_title)
        inventory_layout.addWidget(self._inventory_list, 1)
        inventory_panel = QFrame()
        inventory_panel.setObjectName("shopInventoryPanel")
        inventory_panel.setLayout(inventory_layout)

        selected_title = QLabel("Selected item")
        selected_title.setObjectName("shopSectionTitle")
        self._inventory_detail_label = QLabel("Select an owned item to equip it.")
        self._inventory_detail_label.setObjectName("shopDetailMeta")
        self._inventory_detail_label.setWordWrap(True)
        self._equip_button = QPushButton("Equip")
        self._equip_button.setObjectName("shopPrimaryButton")
        self._equip_button.setIcon(fluent_icon("\ue73e"))
        self._equip_button.clicked.connect(self._request_equip_selected)
        self._equip_button.setEnabled(False)

        loadout_title = QLabel("Current loadout")
        loadout_title.setObjectName("shopSectionTitle")
        loadout_layout = QVBoxLayout()
        loadout_layout.setContentsMargins(0, 0, 0, 0)
        loadout_layout.setSpacing(6)
        for slot in EquipmentSlot:
            loadout_layout.addWidget(self._build_loadout_row(slot))

        detail_layout = QVBoxLayout()
        detail_layout.setContentsMargins(20, 16, 20, 16)
        detail_layout.setSpacing(10)
        detail_layout.addWidget(selected_title)
        detail_layout.addWidget(self._inventory_detail_label)
        detail_layout.addWidget(self._equip_button, 0, Qt.AlignmentFlag.AlignRight)
        detail_layout.addSpacing(12)
        detail_layout.addWidget(loadout_title)
        detail_layout.addLayout(loadout_layout)
        detail_layout.addStretch(1)
        detail_panel = QFrame()
        detail_panel.setObjectName("shopDetailPanel")
        detail_panel.setLayout(detail_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("shopSplitter")
        splitter.addWidget(inventory_panel)
        splitter.addWidget(detail_panel)
        splitter.setSizes([390, 410])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        page = QWidget()
        page.setObjectName("shopPage")
        page.setLayout(layout)
        return page

    def _build_loadout_row(self, slot: EquipmentSlot) -> QFrame:
        slot_label = QLabel(slot.value.title())
        slot_label.setObjectName("shopSlotName")
        item_label = QLabel("Empty")
        item_label.setObjectName("shopSlotItem")
        item_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        button = QPushButton()
        button.setObjectName("shopRowIconButton")
        button.setIcon(fluent_icon("\ue711"))
        button.setToolTip(f"Unequip {slot.value} item")
        button.setEnabled(False)
        button.clicked.connect(
            lambda checked=False, selected_slot=slot: self.unequip_requested.emit(
                selected_slot
            )
        )
        self._loadout_labels[slot] = item_label
        self._unequip_buttons[slot] = button

        layout = QHBoxLayout()
        layout.setContentsMargins(12, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(slot_label)
        layout.addStretch(1)
        layout.addWidget(item_label)
        layout.addWidget(button)
        row = QFrame()
        row.setObjectName("shopLoadoutRow")
        row.setLayout(layout)
        return row

    def current_query(self) -> CatalogQuery:
        """Return the current closed catalog query represented by the controls."""
        category_value = self._category_filter.currentData()
        ownership_value = self._ownership_filter.currentData()
        sort_value = self._sort_filter.currentData()
        if category_value is not None and not isinstance(category_value, str):
            raise RuntimeError("The category control contains an invalid value.")
        if not isinstance(ownership_value, str):
            raise RuntimeError("The ownership control contains an invalid value.")
        if not isinstance(sort_value, str):
            raise RuntimeError("The sort control contains an invalid value.")
        try:
            category = (
                ShopItemCategory(category_value) if category_value is not None else None
            )
            ownership = CatalogOwnershipFilter(ownership_value)
            sort = CatalogSort(sort_value)
        except ValueError as error:
            raise RuntimeError("A shop filter contains an unknown value.") from error
        availability = (
            CatalogAvailability.AVAILABLE
            if ownership is CatalogOwnershipFilter.UNOWNED
            else None
        )
        return CatalogQuery(
            category=category,
            availability=availability,
            ownership=ownership,
            sort=sort,
        )

    def update_result(self, result: ShopWorkerResult) -> None:
        """Render one completed operation and its fully refreshed snapshot."""
        if not isinstance(result, ShopWorkerResult):
            raise TypeError("result must be a ShopWorkerResult value.")
        self.update_snapshot(result.snapshot)
        if result.purchase is not None:
            self.set_notice(_purchase_message(result.purchase.decision))
        elif result.equipment is not None:
            self.set_notice(_equipment_message(result.equipment.decision))
        else:
            self.set_notice("Shop and wardrobe refreshed.")

    def update_snapshot(self, snapshot: ShopUiSnapshot) -> None:
        """Render sanitized catalog, inventory, and loadout state."""
        if not isinstance(snapshot, ShopUiSnapshot):
            raise TypeError("snapshot must be a ShopUiSnapshot value.")
        selected_shop_id = _selected_item_id(self._catalog_list, _SHOP_ITEM_ROLE)
        selected_inventory_id = _selected_item_id(
            self._inventory_list,
            _INVENTORY_ITEM_ROLE,
        )
        self._snapshot = snapshot
        self._shop_items = {item.item_id: item for item in snapshot.browse.items}
        self._inventory_items = {item.item_id: item for item in snapshot.inventory}
        self._summary_label.setText(
            f"Level {snapshot.browse.level}  |  {snapshot.browse.balance} currency"
        )
        self._render_catalog(selected_shop_id)
        self._render_inventory(selected_inventory_id)
        self._render_loadout()
        if snapshot.browse.catalog_failure is not None:
            self.set_notice(
                "The trusted catalog could not be loaded. "
                "The wardrobe remains available.",
                error=True,
            )

    def set_busy(self, busy: bool) -> None:
        """Prevent overlapping mutations while a shop operation is active."""
        if not isinstance(busy, bool):
            raise TypeError("busy must be a boolean.")
        self._refresh_button.setEnabled(not busy)
        self._category_filter.setEnabled(not busy)
        self._ownership_filter.setEnabled(not busy)
        self._sort_filter.setEnabled(not busy)
        self._purchase_button.setEnabled(not busy and self._purchase_allowed())
        self._equip_button.setEnabled(not busy and self._equip_allowed())
        for slot, button in self._unequip_buttons.items():
            button.setEnabled(not busy and self._slot_is_occupied(slot))
        if busy:
            self.set_notice("Updating the trusted shop state...")

    def set_notice(self, message: str, *, error: bool = False) -> None:
        """Show one concise sanitized operation status."""
        self._notice_label.setText(message.strip() or "Shop and wardrobe are ready.")
        self._notice_label.setProperty("semantic", "error" if error else "normal")
        self._notice_label.style().unpolish(self._notice_label)
        self._notice_label.style().polish(self._notice_label)

    def _emit_refresh(self, *_args: object) -> None:
        self.refresh_requested.emit(self.current_query())

    def _render_catalog(self, selected_item_id: str | None) -> None:
        self._catalog_list.clear()
        for item in self._shop_items.values():
            status = "Owned" if item.owned else _catalog_item_status(item)
            row = QListWidgetItem(
                f"{item.display_name}\n{item.price} currency  |  "
                f"{item.slot.value.title()}  |  {status}"
            )
            row.setData(_SHOP_ITEM_ROLE, item)
            row.setSizeHint(QSize(0, 58))
            self._catalog_list.addItem(row)
        if not self._shop_items:
            _add_empty_row(self._catalog_list, "No catalog items match this view.")
            self._clear_catalog_detail()
            return
        _restore_selection(self._catalog_list, selected_item_id, _SHOP_ITEM_ROLE)
        self._apply_text_filter(self._search_input.text())

    def _render_inventory(self, selected_item_id: str | None) -> None:
        self._inventory_list.clear()
        for item in self._inventory_items.values():
            name = item.display_name or item.item_id
            slot = item.slot.value.title() if item.slot is not None else "Unknown slot"
            status = "Equipped" if item.equipped else "Owned"
            if not item.present_in_catalog:
                status = "Catalog entry unavailable"
            row = QListWidgetItem(f"{name}\n{slot}  |  {status}")
            row.setData(_INVENTORY_ITEM_ROLE, item)
            row.setSizeHint(QSize(0, 56))
            self._inventory_list.addItem(row)
        if not self._inventory_items:
            _add_empty_row(self._inventory_list, "No owned items yet.")
            self._clear_inventory_detail()
            return
        _restore_selection(
            self._inventory_list,
            selected_item_id,
            _INVENTORY_ITEM_ROLE,
        )

    def _render_loadout(self) -> None:
        snapshot = self._snapshot
        for slot in EquipmentSlot:
            equipped = snapshot.loadout.item_for(slot) if snapshot is not None else None
            self._loadout_labels[slot].setText(
                (equipped.display_name or equipped.item_id) if equipped else "Empty"
            )
            self._unequip_buttons[slot].setEnabled(equipped is not None)

    def _apply_text_filter(self, text: str) -> None:
        query = text.strip().casefold()
        first_visible: QListWidgetItem | None = None
        for index in range(self._catalog_list.count()):
            row = self._catalog_list.item(index)
            item = row.data(_SHOP_ITEM_ROLE)
            visible = isinstance(item, ShopItemView) and (
                not query or query in item.display_name.casefold()
            )
            row.setHidden(not visible)
            if visible and first_visible is None:
                first_visible = row
        current = self._catalog_list.currentItem()
        if current is None or current.isHidden():
            self._catalog_list.setCurrentItem(first_visible)

    def _show_catalog_selection(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        del previous
        item = current.data(_SHOP_ITEM_ROLE) if current is not None else None
        if not isinstance(item, ShopItemView):
            self._clear_catalog_detail()
            return
        self._item_name_label.setText(item.display_name)
        self._item_meta_label.setText(
            f"{item.category.value.title()}  |  {item.slot.value.title()} slot  |  "
            f"Requires level {item.required_level}"
        )
        self._item_price_label.setText(f"{item.price} currency")
        self._item_status_label.setText(_catalog_item_detail(item))
        self._item_status_label.setProperty("semantic", _catalog_item_semantic(item))
        _refresh_style(self._item_status_label)
        self._purchase_button.setEnabled(self._purchase_allowed())

    def _show_inventory_selection(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        del previous
        item = current.data(_INVENTORY_ITEM_ROLE) if current is not None else None
        if not isinstance(item, ShopInventoryItemView):
            self._clear_inventory_detail()
            return
        name = item.display_name or item.item_id
        source = item.acquisition_source.value.replace("_", " ").title()
        if not item.present_in_catalog:
            detail = f"{name}\nOwned via {source}. Its catalog entry is unavailable."
        elif item.equipped:
            detail = f"{name}\nCurrently equipped in the {item.slot.value} slot."
        elif item.visual_compatible is not True:
            detail = (
                f"{name}\nOwned via {source}. Its approved visual layer is unavailable."
            )
        else:
            detail = f"{name}\nOwned via {source}. Ready to equip."
        self._inventory_detail_label.setText(detail)
        self._equip_button.setEnabled(self._equip_allowed())

    def _request_purchase_selected(self) -> None:
        item = _selected_shop_item(self._catalog_list)
        if item is None or not self._purchase_allowed():
            return
        if self._purchase_confirmation(item):
            self.purchase_requested.emit(item.item_id)

    def _request_equip_selected(self) -> None:
        item = _selected_inventory_item(self._inventory_list)
        if item is not None and self._equip_allowed():
            self.equip_requested.emit(item.item_id)

    def _purchase_allowed(self) -> bool:
        item = _selected_shop_item(self._catalog_list)
        return bool(
            item is not None
            and not item.owned
            and item.availability is CatalogAvailability.AVAILABLE
            and item.level_met
            and item.affordable
            and item.visual_compatible
        )

    def _equip_allowed(self) -> bool:
        item = _selected_inventory_item(self._inventory_list)
        if item is None or item.equipped or not item.present_in_catalog:
            return False
        return item.visual_compatible is True

    def _slot_is_occupied(self, slot: EquipmentSlot) -> bool:
        return (
            self._snapshot is not None
            and self._snapshot.loadout.item_for(slot) is not None
        )

    def _clear_catalog_detail(self) -> None:
        self._item_name_label.setText("Select an item")
        self._item_meta_label.setText("Catalog details will appear here.")
        self._item_price_label.setText("-- currency")
        self._item_status_label.setText("No item selected.")
        self._item_status_label.setProperty("semantic", "normal")
        _refresh_style(self._item_status_label)
        self._purchase_button.setEnabled(False)

    def _clear_inventory_detail(self) -> None:
        self._inventory_detail_label.setText("Select an owned item to equip it.")
        self._equip_button.setEnabled(False)

    def _confirm_purchase(self, item: ShopItemView) -> bool:
        answer = QMessageBox.question(
            self,
            "Confirm purchase",
            f"Purchase {item.display_name} for {item.price} currency?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer is QMessageBox.StandardButton.Yes


def _build_list(object_name: str) -> QListWidget:
    widget = QListWidget()
    widget.setObjectName(object_name)
    widget.setAlternatingRowColors(False)
    widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setUniformItemSizes(True)
    return widget


def _add_empty_row(widget: QListWidget, text: str) -> None:
    row = QListWidgetItem(text)
    row.setFlags(Qt.ItemFlag.NoItemFlags)
    row.setSizeHint(QSize(0, 52))
    widget.addItem(row)


def _restore_selection(
    widget: QListWidget,
    item_id: str | None,
    role: Qt.ItemDataRole,
) -> None:
    selected: QListWidgetItem | None = None
    for index in range(widget.count()):
        row = widget.item(index)
        value = row.data(role)
        if getattr(value, "item_id", None) == item_id:
            selected = row
            break
        if selected is None and value is not None:
            selected = row
    widget.setCurrentItem(selected)


def _selected_item_id(widget: QListWidget, role: Qt.ItemDataRole) -> str | None:
    row = widget.currentItem()
    value = row.data(role) if row is not None else None
    item_id = getattr(value, "item_id", None)
    return item_id if isinstance(item_id, str) else None


def _selected_shop_item(widget: QListWidget) -> ShopItemView | None:
    row = widget.currentItem()
    value = row.data(_SHOP_ITEM_ROLE) if row is not None else None
    return value if isinstance(value, ShopItemView) else None


def _selected_inventory_item(widget: QListWidget) -> ShopInventoryItemView | None:
    row = widget.currentItem()
    value = row.data(_INVENTORY_ITEM_ROLE) if row is not None else None
    return value if isinstance(value, ShopInventoryItemView) else None


def _catalog_item_status(item: ShopItemView) -> str:
    if item.availability is not CatalogAvailability.AVAILABLE:
        return "Unavailable"
    if not item.visual_compatible:
        return "Visual unavailable"
    if not item.level_met:
        return f"Level {item.required_level} required"
    if not item.affordable:
        return "Insufficient currency"
    return "Available"


def _catalog_item_detail(item: ShopItemView) -> str:
    if item.owned:
        return "Owned. Manage this item from Wardrobe."
    if item.availability is not CatalogAvailability.AVAILABLE:
        return "This item is not currently available for purchase."
    if not item.visual_compatible:
        return "Its approved visual layer is unavailable for the baseline idle view."
    if not item.level_met:
        return f"Reach level {item.required_level} before purchasing this item."
    if not item.affordable:
        return "Akiha does not have enough currency for this item."
    return "Available to purchase. Ownership is permanent and non-stackable."


def _catalog_item_semantic(item: ShopItemView) -> str:
    if item.owned:
        return "success"
    if _catalog_item_status(item) == "Available":
        return "available"
    return "warning"


def _purchase_message(decision: PurchaseDecision) -> str:
    messages = {
        PurchaseDecision.COMPLETED: "Purchase complete. The item is now in Wardrobe.",
        PurchaseDecision.ALREADY_OWNED: "That item is already owned.",
        PurchaseDecision.INSUFFICIENT_FUNDS: "Akiha does not have enough currency.",
        PurchaseDecision.LEVEL_REQUIRED: "Akiha has not reached the required level.",
        PurchaseDecision.ITEM_UNAVAILABLE: "That item is currently unavailable.",
        PurchaseDecision.ITEM_NOT_FOUND: "That catalog item no longer exists.",
    }
    return messages[decision]


def _equipment_message(decision: EquipmentDecision) -> str:
    messages = {
        EquipmentDecision.EQUIPPED: "Item equipped. The wardrobe is up to date.",
        EquipmentDecision.UNEQUIPPED: "Item unequipped. Ownership was preserved.",
        EquipmentDecision.ALREADY_EQUIPPED: "That item is already equipped.",
        EquipmentDecision.EMPTY_SLOT: "That equipment slot is already empty.",
        EquipmentDecision.ITEM_NOT_FOUND: "That catalog item no longer exists.",
        EquipmentDecision.NOT_OWNED: "Only owned items can be equipped.",
        EquipmentDecision.VISUAL_INCOMPATIBLE: (
            "That item's approved visual layer is not compatible yet."
        ),
    }
    return messages[decision]


def _refresh_style(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
