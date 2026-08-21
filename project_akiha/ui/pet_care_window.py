"""Compact care surface for Akiha's persistent pet state."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from project_akiha.core.pet import (
    CareAction,
    PetCareEvaluation,
    PetRewardDecision,
    PetStateRecord,
    WellbeingBand,
    wellbeing_band,
    xp_required_for_level,
)
from project_akiha.ui.fluent_icons import fluent_icon
from project_akiha.ui.theme import pet_care_stylesheet


@dataclass(frozen=True, slots=True)
class _NeedPresentation:
    label: str
    icon: str


_NEED_PRESENTATION = {
    "satiety": _NeedPresentation("Satiety", "\uecaf"),
    "energy": _NeedPresentation("Energy", "\ue945"),
    "attention": _NeedPresentation("Attention", "\ue7b7"),
    "affection": _NeedPresentation("Affection", "\ue00b"),
}


class PetCareWindow(QWidget):
    """Display pet wellbeing and emit only explicit typed care requests."""

    refresh_requested = Signal()
    care_action_requested = Signal(object)
    shop_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Akiha Care")
        self.setObjectName("akihaPetCareWindow")
        self.setMinimumSize(480, 560)
        self.resize(520, 620)
        self.setStyleSheet(pet_care_stylesheet())

        self._need_values: dict[str, QLabel] = {}
        self._need_bars: dict[str, QProgressBar] = {}
        self._care_buttons: list[QPushButton] = []

        header = self._build_header()
        progression = self._build_progression_panel()
        needs = self._build_needs_panel()
        actions = self._build_actions_panel()

        self._notice_label = QLabel("Loading Akiha's care status...")
        self._notice_label.setObjectName("careNotice")
        self._notice_label.setWordWrap(True)

        body_layout = QVBoxLayout()
        body_layout.setContentsMargins(20, 18, 20, 18)
        body_layout.setSpacing(14)
        body_layout.addWidget(progression)
        body_layout.addWidget(needs, 1)
        body_layout.addWidget(actions)
        body_layout.addWidget(self._notice_label)
        body = QFrame()
        body.setObjectName("careBody")
        body.setLayout(body_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(body, 1)
        self.setLayout(layout)

    def _build_header(self) -> QFrame:
        icon_label = QLabel()
        icon_label.setPixmap(fluent_icon("\ue00b", 20).pixmap(22, 22))
        title = QLabel("Akiha Care")
        title.setObjectName("careTitle")
        self._summary_label = QLabel("Persistent companion status")
        self._summary_label.setObjectName("careSummary")

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(9)
        title_row.addWidget(icon_label)
        title_row.addWidget(title)
        title_row.addStretch(1)

        heading = QVBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(5)
        heading.addLayout(title_row)
        heading.addWidget(self._summary_label)

        shop = QPushButton()
        shop.setObjectName("careIconButton")
        shop.setIcon(fluent_icon("\ue719"))
        shop.setToolTip("Open shop and wardrobe")
        shop.clicked.connect(self.shop_requested.emit)

        refresh = QPushButton()
        refresh.setObjectName("careIconButton")
        refresh.setIcon(fluent_icon("\ue72c"))
        refresh.setToolTip("Refresh care status")
        refresh.clicked.connect(self.refresh_requested.emit)
        self._refresh_button = refresh

        close = QPushButton()
        close.setObjectName("careIconButton")
        close.setIcon(fluent_icon("\ue8bb"))
        close.setToolTip("Close")
        close.clicked.connect(self.close)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(20, 16, 14, 16)
        header_layout.setSpacing(8)
        header_layout.addLayout(heading)
        header_layout.addStretch(1)
        header_layout.addWidget(shop, 0, Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(refresh, 0, Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        header = QFrame()
        header.setObjectName("careHeader")
        header.setLayout(header_layout)
        return header

    def _build_progression_panel(self) -> QFrame:
        self._level_label = QLabel("Level 1")
        self._level_label.setObjectName("careLevel")
        self._currency_label = QLabel("0 currency")
        self._currency_label.setObjectName("careCurrency")
        self._xp_label = QLabel("0 / 25 XP")
        self._xp_label.setObjectName("careMeta")
        self._xp_bar = QProgressBar()
        self._xp_bar.setObjectName("careXpBar")
        self._xp_bar.setRange(0, 25)
        self._xp_bar.setValue(0)
        self._xp_bar.setTextVisible(False)

        heading = QHBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.addWidget(self._level_label)
        heading.addStretch(1)
        heading.addWidget(self._currency_label)

        xp_row = QHBoxLayout()
        xp_row.setContentsMargins(0, 0, 0, 0)
        xp_row.addWidget(QLabel("Progress"))
        xp_row.addStretch(1)
        xp_row.addWidget(self._xp_label)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(9)
        layout.addLayout(heading)
        layout.addLayout(xp_row)
        layout.addWidget(self._xp_bar)
        panel = QFrame()
        panel.setObjectName("careProgressionPanel")
        panel.setLayout(layout)
        return panel

    def _build_needs_panel(self) -> QFrame:
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for key, presentation in _NEED_PRESENTATION.items():
            layout.addWidget(self._build_need_row(key, presentation))
        panel = QFrame()
        panel.setObjectName("careNeedsPanel")
        panel.setLayout(layout)
        return panel

    def _build_need_row(
        self,
        key: str,
        presentation: _NeedPresentation,
    ) -> QFrame:
        icon = QLabel()
        icon.setObjectName("careNeedIcon")
        icon.setPixmap(fluent_icon(presentation.icon, 16).pixmap(20, 20))
        label = QLabel(presentation.label)
        label.setObjectName("careNeedLabel")
        value = QLabel("--")
        value.setObjectName("careNeedValue")
        bar = QProgressBar()
        bar.setObjectName("careNeedBar")
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setProperty("semantic", "stable")
        self._need_values[key] = value
        self._need_bars[key] = bar

        heading = QHBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(8)
        heading.addWidget(icon)
        heading.addWidget(label)
        heading.addStretch(1)
        heading.addWidget(value)

        layout = QVBoxLayout()
        layout.setContentsMargins(14, 11, 14, 12)
        layout.setSpacing(8)
        layout.addLayout(heading)
        layout.addWidget(bar)
        row = QFrame()
        row.setObjectName("careNeedRow")
        row.setLayout(layout)
        return row

    def _build_actions_panel(self) -> QFrame:
        title = QLabel("Care")
        title.setObjectName("careSectionTitle")
        buttons = (
            self._care_button("Feed", "\uecaf", CareAction.FEED),
            self._care_button("Rest", "\ue708", CareAction.REST),
            self._care_button("Spend time", "\ue77b", CareAction.SPEND_TIME),
        )
        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)
        for button in buttons:
            button_row.addWidget(button, 1)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addLayout(button_row)
        panel = QFrame()
        panel.setObjectName("careActionsPanel")
        panel.setLayout(layout)
        return panel

    def _care_button(self, text: str, glyph: str, action: CareAction) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("careActionButton")
        button.setIcon(fluent_icon(glyph))
        button.clicked.connect(
            lambda checked=False, requested=action: self._emit_care_action(requested)
        )
        self._care_buttons.append(button)
        return button

    def _emit_care_action(self, action: CareAction) -> None:
        self.care_action_requested.emit(action)

    def update_record(self, record: PetStateRecord) -> None:
        """Render one validated durable pet-state record."""
        if not isinstance(record, PetStateRecord):
            raise TypeError("record must be a PetStateRecord value.")
        state = record.state
        wellbeing = state.wellbeing
        values = {
            "satiety": wellbeing.satiety,
            "energy": wellbeing.energy,
            "attention": wellbeing.attention,
            "affection": wellbeing.affection,
        }
        for key, value in values.items():
            self._need_values[key].setText(f"{value}%")
            self._need_bars[key].setValue(value)
            self._set_bar_semantic(self._need_bars[key], wellbeing_band(value))

        progression = state.progression
        current_floor = xp_required_for_level(progression.level)
        next_threshold = xp_required_for_level(progression.level + 1)
        earned = progression.xp - current_floor
        required = next_threshold - current_floor
        self._level_label.setText(f"Level {progression.level}")
        self._currency_label.setText(f"{progression.currency} currency")
        self._xp_label.setText(f"{earned} / {required} XP")
        self._xp_bar.setRange(0, required)
        self._xp_bar.setValue(earned)
        self._summary_label.setText(self._summary_for(values))

    def show_care_result(self, evaluation: PetCareEvaluation) -> None:
        """Render one committed care outcome without changing domain state."""
        if not isinstance(evaluation, PetCareEvaluation):
            raise TypeError("evaluation must be a PetCareEvaluation value.")
        self.update_record(evaluation.record)
        action = evaluation.care_outcome.action
        if not evaluation.care_outcome.changed:
            message = f"{_action_label(action)} is already fully satisfied."
        elif evaluation.reward_outcome.granted:
            grant = evaluation.reward_outcome.grant
            assert grant is not None
            message = (
                f"{_action_label(action)} complete. "
                f"+{grant.xp_awarded} XP, +{grant.currency_awarded} currency."
            )
        elif evaluation.reward_outcome.decision is PetRewardDecision.COOLDOWN:
            message = f"{_action_label(action)} complete. Reward cooldown is active."
        elif evaluation.reward_outcome.decision is PetRewardDecision.DAILY_CAP:
            message = f"{_action_label(action)} complete. Daily care rewards reached."
        else:
            message = f"{_action_label(action)} complete."
        self.set_notice(message)

    def set_busy(self, busy: bool) -> None:
        """Prevent overlapping mutations while one service operation is active."""
        if not isinstance(busy, bool):
            raise TypeError("busy must be a boolean.")
        self._refresh_button.setEnabled(not busy)
        for button in self._care_buttons:
            button.setEnabled(not busy)
        if busy:
            self.set_notice("Updating Akiha's care status...")

    def set_notice(self, message: str, *, error: bool = False) -> None:
        """Show a concise operation result or sanitized error."""
        self._notice_label.setText(message.strip() or "Care status is ready.")
        self._notice_label.setProperty("semantic", "error" if error else "normal")
        self._notice_label.style().unpolish(self._notice_label)
        self._notice_label.style().polish(self._notice_label)

    @staticmethod
    def _set_bar_semantic(bar: QProgressBar, band: WellbeingBand) -> None:
        bar.setProperty("semantic", band.value)
        bar.style().unpolish(bar)
        bar.style().polish(bar)

    @staticmethod
    def _summary_for(values: dict[str, int]) -> str:
        minimum = min(values.values())
        if minimum <= 25:
            return "Akiha needs care"
        if minimum <= 50:
            return "Akiha could use some attention"
        return "Akiha is doing well"


def _action_label(action: CareAction) -> str:
    if action is CareAction.FEED:
        return "Feeding"
    if action is CareAction.REST:
        return "Rest"
    if action is CareAction.SPEND_TIME:
        return "Time together"
    raise TypeError("action must be a CareAction value.")
