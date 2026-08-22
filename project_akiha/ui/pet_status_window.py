"""Read-only Akiha status surface."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from project_akiha.services.pet_status import PetStatusSnapshot
from project_akiha.ui.fluent_icons import fluent_icon
from project_akiha.ui.theme import pet_status_stylesheet


class PetStatusWindow(QWidget):
    """Answer how Akiha is doing without exposing mutation controls."""

    refresh_requested = Signal()
    care_requested = Signal()
    shop_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Akiha Status")
        self.setObjectName("akihaPetStatusWindow")
        self.setMinimumSize(520, 620)
        self.resize(560, 680)
        self.setStyleSheet(pet_status_stylesheet())
        self._need_values: dict[str, QLabel] = {}
        self._need_bars: dict[str, QProgressBar] = {}
        self._runtime_values: dict[str, QLabel] = {}
        self._diagnostic_values: dict[str, QLabel] = {}

        body_layout = QVBoxLayout()
        body_layout.setContentsMargins(20, 16, 20, 18)
        body_layout.setSpacing(12)
        body_layout.addWidget(self._build_progression_panel())
        body_layout.addWidget(self._build_needs_panel())
        body_layout.addWidget(self._build_runtime_panel())
        body_layout.addWidget(self._build_diagnostics_panel(), 1)
        self._notice_label = QLabel("Loading Akiha's status...")
        self._notice_label.setObjectName("careNotice")
        self._notice_label.setWordWrap(True)
        body_layout.addWidget(self._notice_label)
        body = QFrame()
        body.setObjectName("careBody")
        body.setLayout(body_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_header())
        layout.addWidget(body, 1)
        self.setLayout(layout)

    def _build_header(self) -> QFrame:
        icon = QLabel()
        icon.setPixmap(fluent_icon("\ue9d9", 20).pixmap(22, 22))
        title = QLabel("Akiha Status")
        title.setObjectName("careTitle")
        self._summary_label = QLabel("Current companion state")
        self._summary_label.setObjectName("careSummary")
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(9)
        title_row.addWidget(icon)
        title_row.addWidget(title)
        title_row.addStretch(1)
        heading = QVBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(5)
        heading.addLayout(title_row)
        heading.addWidget(self._summary_label)

        care = self._icon_button("\ue00b", "Open care", self.care_requested.emit)
        shop = self._icon_button(
            "\ue719", "Open shop and appearances", self.shop_requested.emit
        )
        refresh = self._icon_button(
            "\ue72c", "Refresh status", self.refresh_requested.emit
        )
        self._refresh_button = refresh
        close = self._icon_button("\ue8bb", "Close", self.close)

        layout = QHBoxLayout()
        layout.setContentsMargins(20, 16, 14, 16)
        layout.setSpacing(8)
        layout.addLayout(heading)
        layout.addStretch(1)
        for button in (care, shop, refresh, close):
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)
        frame = QFrame()
        frame.setObjectName("careHeader")
        frame.setLayout(layout)
        return frame

    def _build_progression_panel(self) -> QFrame:
        self._level_label = QLabel("Level --")
        self._level_label.setObjectName("careLevel")
        self._currency_label = QLabel("-- currency")
        self._currency_label.setObjectName("careCurrency")
        self._xp_label = QLabel("-- XP")
        self._xp_label.setObjectName("careMeta")
        layout = QHBoxLayout()
        layout.setContentsMargins(16, 14, 16, 14)
        layout.addWidget(self._level_label)
        layout.addStretch(1)
        layout.addWidget(self._xp_label)
        layout.addWidget(self._currency_label)
        frame = QFrame()
        frame.setObjectName("careProgressionPanel")
        frame.setLayout(layout)
        return frame

    def _build_needs_panel(self) -> QFrame:
        grid = QGridLayout()
        grid.setContentsMargins(14, 12, 14, 12)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        for row, (key, label) in enumerate(
            (
                ("satiety", "Satiety"),
                ("energy", "Energy"),
                ("attention", "Attention"),
                ("affection", "Affection"),
            )
        ):
            name = QLabel(label)
            name.setObjectName("careNeedLabel")
            bar = QProgressBar()
            bar.setObjectName("careNeedBar")
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            value = QLabel("--")
            value.setObjectName("careNeedValue")
            self._need_bars[key] = bar
            self._need_values[key] = value
            grid.addWidget(name, row, 0)
            grid.addWidget(bar, row, 1)
            grid.addWidget(value, row, 2)
        frame = QFrame()
        frame.setObjectName("careProgressionPanel")
        frame.setLayout(grid)
        return frame

    def _build_runtime_panel(self) -> QFrame:
        return self._field_panel(
            "Current state",
            (
                ("mood", "Mood"),
                ("presence", "Presence"),
                ("appearance", "Appearance"),
                ("animation", "Animation"),
                ("activity", "Autonomous activity"),
            ),
            self._runtime_values,
            "statusRuntimePanel",
        )

    def _build_diagnostics_panel(self) -> QFrame:
        return self._field_panel(
            "Local system health",
            (
                ("catalog", "Catalog"),
                ("ownership", "Ownership"),
                ("activity", "Activity manifest"),
                ("privacy", "Privacy boundary"),
            ),
            self._diagnostic_values,
            "statusDiagnosticsPanel",
        )

    @staticmethod
    def _field_panel(
        title_text: str,
        fields: tuple[tuple[str, str], ...],
        destination: dict[str, QLabel],
        object_name: str,
    ) -> QFrame:
        title = QLabel(title_text)
        title.setObjectName("careSectionTitle")
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(7)
        for row, (key, label) in enumerate(fields):
            name = QLabel(label)
            name.setObjectName("statusFieldLabel")
            value = QLabel("Not checked")
            value.setObjectName("statusFieldValue")
            value.setWordWrap(True)
            destination[key] = value
            grid.addWidget(name, row, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(value, row, 1)
        grid.setColumnStretch(1, 1)
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 13, 16, 14)
        layout.setSpacing(9)
        layout.addWidget(title)
        layout.addLayout(grid)
        frame = QFrame()
        frame.setObjectName(object_name)
        frame.setLayout(layout)
        return frame

    @staticmethod
    def _icon_button(
        glyph: str,
        tooltip: str,
        callback: Callable[[], None],
    ) -> QPushButton:
        button = QPushButton()
        button.setObjectName("careIconButton")
        button.setIcon(fluent_icon(glyph))
        button.setToolTip(tooltip)
        button.clicked.connect(callback)
        return button

    def update_snapshot(self, snapshot: PetStatusSnapshot) -> None:
        """Render one typed aggregate without exposing any mutation action."""
        if not isinstance(snapshot, PetStatusSnapshot):
            raise TypeError("snapshot must be a PetStatusSnapshot value.")
        pet = snapshot.pet
        self._summary_label.setText(snapshot.headline)
        self._level_label.setText(f"Level {pet.level}")
        self._xp_label.setText(f"{pet.xp} XP")
        self._currency_label.setText(f"{pet.currency} currency")
        for key, value in (
            ("satiety", pet.satiety),
            ("energy", pet.energy),
            ("attention", pet.attention),
            ("affection", pet.affection),
        ):
            self._need_values[key].setText(f"{value}%")
            self._need_bars[key].setValue(value)
            semantic = "critical" if value <= 25 else "low" if value <= 50 else "stable"
            self._need_bars[key].setProperty("semantic", semantic)
            self._refresh_style(self._need_bars[key])
        runtime = snapshot.runtime
        systems = snapshot.systems
        self._runtime_values["mood"].setText(runtime.mood.value.replace("_", " "))
        self._runtime_values["presence"].setText(runtime.user_activity.value)
        self._runtime_values["appearance"].setText(systems.current_appearance_id.value)
        self._runtime_values["animation"].setText(runtime.animation_state.value)
        self._runtime_values["activity"].setText(
            runtime.autonomous_activity_id.value
            if runtime.autonomous_activity_id is not None
            else "None"
        )
        self._diagnostic_values["catalog"].setText(systems.catalog_summary)
        self._diagnostic_values["ownership"].setText(systems.ownership_summary)
        self._diagnostic_values["activity"].setText(systems.activity_summary)
        self._diagnostic_values["privacy"].setText(systems.privacy_summary)
        self._diagnostic_values["privacy"].setObjectName("statusPrivacy")
        self._refresh_style(self._diagnostic_values["privacy"])
        self.set_notice("Status refreshed from local structured state.")

    def set_busy(self, busy: bool) -> None:
        self._refresh_button.setEnabled(not busy)
        if busy:
            self.set_notice("Refreshing Akiha's status...")

    def set_notice(self, message: str, *, error: bool = False) -> None:
        self._notice_label.setText(message.strip() or "Status is ready.")
        self._notice_label.setProperty("semantic", "error" if error else "normal")
        self._refresh_style(self._notice_label)

    @staticmethod
    def _refresh_style(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
