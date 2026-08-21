"""Compact trusted shop and complete-appearance surface for Akiha."""

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

from project_akiha.core.appearance import (
    AppearanceAvailability,
    AppearanceId,
    AppearanceSelectionDecision,
    AppearanceView,
)
from project_akiha.core.shop import (
    CatalogAvailability,
    CatalogOwnershipFilter,
    CatalogQuery,
    CatalogSort,
    PurchaseDecision,
    ShopItemCategory,
    ShopItemView,
)
from project_akiha.ui.fluent_icons import FluentComboBox, fluent_icon
from project_akiha.ui.shop_worker import ShopUiSnapshot, ShopWorkerResult
from project_akiha.ui.theme import shop_window_stylesheet

_SHOP_ITEM_ROLE = Qt.ItemDataRole.UserRole
_APPEARANCE_ROLE = Qt.ItemDataRole.UserRole


class ShopWindow(QWidget):
    """Present trusted products and complete appearance selection."""

    refresh_requested = Signal(object)
    purchase_requested = Signal(str)
    appearance_select_requested = Signal(object)

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
        self._appearances: dict[AppearanceId, AppearanceView] = {}

        self._tabs = QTabWidget()
        self._tabs.setObjectName("shopTabs")
        self._tabs.setDocumentMode(True)
        self._tabs.addTab(self._build_shop_page(), "Shop")
        self._tabs.addTab(self._build_appearance_page(), "Appearance")

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
        layout.addWidget(self._build_header())
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
        self._refresh_button.setToolTip("Refresh shop and appearances")
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
            fluent_icon("\ue721"), QLineEdit.ActionPosition.LeadingPosition
        )
        self._search_input.textChanged.connect(self._apply_text_filter)
        self._category_filter = FluentComboBox()
        self._category_filter.setObjectName("shopFilter")
        self._category_filter.setFixedWidth(140)
        self._category_filter.addItem("All categories", None)
        self._category_filter.addItem("Appearances", ShopItemCategory.APPEARANCE.value)
        self._category_filter.currentIndexChanged.connect(self._emit_refresh)
        self._ownership_filter = FluentComboBox()
        self._ownership_filter.setObjectName("shopFilter")
        self._ownership_filter.setFixedWidth(155)
        self._ownership_filter.addItem("All items", CatalogOwnershipFilter.ALL.value)
        self._ownership_filter.addItem(
            "Available to buy", CatalogOwnershipFilter.UNOWNED.value
        )
        self._ownership_filter.addItem("Owned", CatalogOwnershipFilter.OWNED.value)
        self._ownership_filter.currentIndexChanged.connect(self._emit_refresh)
        self._sort_filter = FluentComboBox()
        self._sort_filter.setObjectName("shopFilter")
        self._sort_filter.setFixedWidth(170)
        self._sort_filter.addItem("Name", CatalogSort.NAME.value)
        self._sort_filter.addItem(
            "Price: low to high", CatalogSort.PRICE_LOW_TO_HIGH.value
        )
        self._sort_filter.addItem(
            "Price: high to low", CatalogSort.PRICE_HIGH_TO_LOW.value
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
        detail = _detail_panel(
            self._item_name_label,
            self._item_meta_label,
            self._item_price_label,
            self._item_status_label,
            self._purchase_button,
        )
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("shopSplitter")
        splitter.addWidget(self._catalog_list)
        splitter.addWidget(detail)
        splitter.setSizes([430, 330])
        page_layout = QVBoxLayout()
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        page_layout.addWidget(filter_frame)
        page_layout.addWidget(splitter, 1)
        page = QWidget()
        page.setObjectName("shopPage")
        page.setLayout(page_layout)
        return page

    def _build_appearance_page(self) -> QWidget:
        self._appearance_list = _build_list("shopAppearanceList")
        self._appearance_list.currentItemChanged.connect(
            self._show_appearance_selection
        )
        self._appearance_name_label = QLabel("Select an appearance")
        self._appearance_name_label.setObjectName("shopDetailTitle")
        self._appearance_status_label = QLabel(
            "Complete approved appearance sets will appear here."
        )
        self._appearance_status_label.setObjectName("shopItemStatus")
        self._appearance_status_label.setWordWrap(True)
        self._select_appearance_button = QPushButton("Use appearance")
        self._select_appearance_button.setObjectName("shopPrimaryButton")
        self._select_appearance_button.setIcon(fluent_icon("\ue73e"))
        self._select_appearance_button.clicked.connect(
            self._request_appearance_selected
        )
        self._select_appearance_button.setEnabled(False)
        detail = _detail_panel(
            self._appearance_name_label,
            self._appearance_status_label,
            self._select_appearance_button,
        )
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("shopSplitter")
        splitter.addWidget(self._appearance_list)
        splitter.addWidget(detail)
        splitter.setSizes([430, 330])
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        page = QWidget()
        page.setObjectName("shopPage")
        page.setLayout(layout)
        return page

    def current_query(self) -> CatalogQuery:
        category_value = self._category_filter.currentData()
        ownership_value = self._ownership_filter.currentData()
        sort_value = self._sort_filter.currentData()
        category = (
            ShopItemCategory(category_value) if category_value is not None else None
        )
        ownership = CatalogOwnershipFilter(ownership_value)
        return CatalogQuery(
            category=category,
            availability=(
                CatalogAvailability.AVAILABLE
                if ownership is CatalogOwnershipFilter.UNOWNED
                else None
            ),
            ownership=ownership,
            sort=CatalogSort(sort_value),
        )

    def update_result(self, result: ShopWorkerResult) -> None:
        if not isinstance(result, ShopWorkerResult):
            raise TypeError("result must be a ShopWorkerResult value.")
        self.update_snapshot(result.snapshot)
        if result.purchase is not None:
            self.set_notice(_purchase_message(result.purchase.decision))
        elif result.appearance is not None:
            self.set_notice(_appearance_message(result.appearance.decision))
        else:
            self.set_notice("Shop and appearances refreshed.")

    def update_snapshot(self, snapshot: ShopUiSnapshot) -> None:
        if not isinstance(snapshot, ShopUiSnapshot):
            raise TypeError("snapshot must be a ShopUiSnapshot value.")
        selected_item = _selected_id(self._catalog_list, _SHOP_ITEM_ROLE, "item_id")
        selected_appearance = _selected_id(
            self._appearance_list, _APPEARANCE_ROLE, "appearance_id"
        )
        self._snapshot = snapshot
        self._shop_items = {item.item_id: item for item in snapshot.browse.items}
        self._appearances = {item.appearance_id: item for item in snapshot.appearances}
        self._summary_label.setText(
            f"Level {snapshot.browse.level}  |  {snapshot.browse.balance} currency"
        )
        self._render_catalog(selected_item)
        self._render_appearances(selected_appearance)
        if snapshot.browse.catalog_failure is not None:
            self.set_notice(
                "The trusted catalog could not be loaded. "
                "Appearance selection remains available.",
                error=True,
            )

    def set_busy(self, busy: bool) -> None:
        self._refresh_button.setEnabled(not busy)
        self._category_filter.setEnabled(not busy)
        self._ownership_filter.setEnabled(not busy)
        self._sort_filter.setEnabled(not busy)
        self._purchase_button.setEnabled(not busy and self._purchase_allowed())
        self._select_appearance_button.setEnabled(
            not busy and self._appearance_select_allowed()
        )
        if busy:
            self.set_notice("Updating the trusted shop state...")

    def set_notice(self, message: str, *, error: bool = False) -> None:
        self._notice_label.setText(message.strip() or "Shop and appearances are ready.")
        self._notice_label.setProperty("semantic", "error" if error else "normal")
        _refresh_style(self._notice_label)

    def _emit_refresh(self, *_args: object) -> None:
        self.refresh_requested.emit(self.current_query())

    def _render_catalog(self, selected_item_id: object) -> None:
        self._catalog_list.clear()
        for item in self._shop_items.values():
            status = "Owned" if item.owned else _catalog_item_status(item)
            row = QListWidgetItem(
                f"{item.display_name}\n{item.price} currency  |  {status}"
            )
            row.setData(_SHOP_ITEM_ROLE, item)
            row.setSizeHint(QSize(0, 58))
            self._catalog_list.addItem(row)
        if not self._shop_items:
            _add_empty_row(
                self._catalog_list, "No appearance products match this view."
            )
            self._clear_catalog_detail()
            return
        _restore_selection(
            self._catalog_list, selected_item_id, _SHOP_ITEM_ROLE, "item_id"
        )
        self._apply_text_filter(self._search_input.text())

    def _render_appearances(self, selected_id: object) -> None:
        self._appearance_list.clear()
        for appearance in self._appearances.values():
            status = _appearance_status(appearance)
            row = QListWidgetItem(f"{appearance.display_name}\n{status}")
            row.setData(_APPEARANCE_ROLE, appearance)
            row.setSizeHint(QSize(0, 58))
            self._appearance_list.addItem(row)
        _restore_selection(
            self._appearance_list,
            selected_id,
            _APPEARANCE_ROLE,
            "appearance_id",
        )

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
        self, current: QListWidgetItem | None, _: object
    ) -> None:
        item = current.data(_SHOP_ITEM_ROLE) if current is not None else None
        if not isinstance(item, ShopItemView):
            self._clear_catalog_detail()
            return
        self._item_name_label.setText(item.display_name)
        self._item_meta_label.setText(
            f"Complete appearance  |  Requires level {item.required_level}"
        )
        self._item_price_label.setText(f"{item.price} currency")
        self._item_status_label.setText(_catalog_item_detail(item))
        self._item_status_label.setProperty("semantic", _catalog_semantic(item))
        _refresh_style(self._item_status_label)
        self._purchase_button.setEnabled(self._purchase_allowed())

    def _show_appearance_selection(
        self, current: QListWidgetItem | None, _: object
    ) -> None:
        appearance = current.data(_APPEARANCE_ROLE) if current is not None else None
        if not isinstance(appearance, AppearanceView):
            self._appearance_name_label.setText("Select an appearance")
            self._appearance_status_label.setText("No appearance selected.")
            self._select_appearance_button.setEnabled(False)
            return
        self._appearance_name_label.setText(appearance.display_name)
        self._appearance_status_label.setText(_appearance_detail(appearance))
        self._appearance_status_label.setProperty(
            "semantic", "success" if appearance.selected else "normal"
        )
        _refresh_style(self._appearance_status_label)
        self._select_appearance_button.setEnabled(self._appearance_select_allowed())

    def _request_purchase_selected(self) -> None:
        item = _selected_shop_item(self._catalog_list)
        if item is not None and self._purchase_allowed():
            if self._purchase_confirmation(item):
                self.purchase_requested.emit(item.item_id)

    def _request_appearance_selected(self) -> None:
        appearance = _selected_appearance(self._appearance_list)
        if appearance is not None and self._appearance_select_allowed():
            self.appearance_select_requested.emit(appearance.appearance_id)

    def _purchase_allowed(self) -> bool:
        item = _selected_shop_item(self._catalog_list)
        return bool(
            item
            and not item.owned
            and item.availability is CatalogAvailability.AVAILABLE
            and item.level_met
            and item.affordable
            and item.asset_available
        )

    def _appearance_select_allowed(self) -> bool:
        appearance = _selected_appearance(self._appearance_list)
        return bool(
            appearance
            and appearance.owned
            and not appearance.selected
            and appearance.availability is AppearanceAvailability.AVAILABLE
        )

    def _clear_catalog_detail(self) -> None:
        self._item_name_label.setText("Select an item")
        self._item_meta_label.setText("Catalog details will appear here.")
        self._item_price_label.setText("-- currency")
        self._item_status_label.setText("No item selected.")
        self._purchase_button.setEnabled(False)

    def _confirm_purchase(self, item: ShopItemView) -> bool:
        answer = QMessageBox.question(
            self,
            "Confirm purchase",
            f"Purchase {item.display_name} for {item.price} currency?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer is QMessageBox.StandardButton.Yes


def _detail_panel(*widgets: QWidget) -> QFrame:
    layout = QVBoxLayout()
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(10)
    for widget in widgets[:-1]:
        layout.addWidget(widget)
    layout.addStretch(1)
    layout.addWidget(widgets[-1], 0, Qt.AlignmentFlag.AlignRight)
    panel = QFrame()
    panel.setObjectName("shopDetailPanel")
    panel.setLayout(layout)
    return panel


def _build_list(object_name: str) -> QListWidget:
    widget = QListWidget()
    widget.setObjectName(object_name)
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
    selected_id: object,
    role: Qt.ItemDataRole,
    attribute: str,
) -> None:
    selected: QListWidgetItem | None = None
    for index in range(widget.count()):
        row = widget.item(index)
        value = row.data(role)
        if getattr(value, attribute, None) == selected_id:
            selected = row
            break
        if selected is None and value is not None:
            selected = row
    widget.setCurrentItem(selected)


def _selected_id(widget: QListWidget, role: Qt.ItemDataRole, attribute: str) -> object:
    row = widget.currentItem()
    value = row.data(role) if row is not None else None
    return getattr(value, attribute, None)


def _selected_shop_item(widget: QListWidget) -> ShopItemView | None:
    row = widget.currentItem()
    value = row.data(_SHOP_ITEM_ROLE) if row is not None else None
    return value if isinstance(value, ShopItemView) else None


def _selected_appearance(widget: QListWidget) -> AppearanceView | None:
    row = widget.currentItem()
    value = row.data(_APPEARANCE_ROLE) if row is not None else None
    return value if isinstance(value, AppearanceView) else None


def _catalog_item_status(item: ShopItemView) -> str:
    if item.availability is not CatalogAvailability.AVAILABLE:
        return "Unavailable"
    if not item.asset_available:
        return "Assets unavailable"
    if not item.level_met:
        return f"Level {item.required_level} required"
    if not item.affordable:
        return "Insufficient currency"
    return "Available"


def _catalog_item_detail(item: ShopItemView) -> str:
    if item.selected:
        return "Owned and currently selected."
    if item.owned:
        return "Owned. Select this complete set from the Appearance tab."
    if item.availability is not CatalogAvailability.AVAILABLE:
        return "This appearance is not currently available for purchase."
    if not item.asset_available:
        return "Its complete approved animation set is not available yet."
    if not item.level_met:
        return f"Reach level {item.required_level} before purchasing this appearance."
    if not item.affordable:
        return "Akiha does not have enough currency for this appearance."
    return "Available to purchase as one complete canonical appearance set."


def _catalog_semantic(item: ShopItemView) -> str:
    if item.owned:
        return "success"
    return "available" if _catalog_item_status(item) == "Available" else "warning"


def _appearance_status(appearance: AppearanceView) -> str:
    if appearance.selected:
        return "Currently selected"
    if appearance.availability is AppearanceAvailability.UNAVAILABLE:
        return "Awaiting approved assets"
    return "Owned" if appearance.owned else "Not owned"


def _appearance_detail(appearance: AppearanceView) -> str:
    if appearance.selected:
        return "This complete canonical appearance is active."
    if appearance.availability is AppearanceAvailability.UNAVAILABLE:
        return (
            "This appearance remains disabled until its complete asset set is approved."
        )
    if not appearance.owned:
        return "Purchase this appearance before selecting it."
    return "Ready to use as Akiha's complete appearance."


def _purchase_message(decision: PurchaseDecision) -> str:
    return {
        PurchaseDecision.COMPLETED: "Purchase complete. The appearance is now owned.",
        PurchaseDecision.ALREADY_OWNED: "That appearance is already owned.",
        PurchaseDecision.INSUFFICIENT_FUNDS: "Akiha does not have enough currency.",
        PurchaseDecision.LEVEL_REQUIRED: "Akiha has not reached the required level.",
        PurchaseDecision.ITEM_UNAVAILABLE: "That appearance is currently unavailable.",
        PurchaseDecision.ITEM_NOT_FOUND: "That catalog item no longer exists.",
    }[decision]


def _appearance_message(decision: AppearanceSelectionDecision) -> str:
    return {
        AppearanceSelectionDecision.SELECTED: "Appearance selected.",
        AppearanceSelectionDecision.ALREADY_SELECTED: (
            "That appearance is already active."
        ),
        AppearanceSelectionDecision.UNAVAILABLE: (
            "That appearance has no approved complete asset set yet."
        ),
        AppearanceSelectionDecision.NOT_OWNED: (
            "Only owned appearances can be selected."
        ),
    }[decision]


def _refresh_style(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
