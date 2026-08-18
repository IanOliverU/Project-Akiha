"""Shared visual tokens for Akiha's desktop UI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AkihaPalette:
    """Keep the uniform-inspired interface palette consistent."""

    window: str = "#1A1D24"
    panel: str = "#22252E"
    control: str = "#2C303C"
    border: str = "#3A3F52"
    text: str = "#E8E9EE"
    muted_text: str = "#9A9FB5"
    primary: str = "#7B7FC4"
    highlight: str = "#9599E0"
    listening_border: str = "#4A5FC7"
    listening: str = "#5B6FD4"
    speaking: str = "#B6BADF"
    success: str = "#78B892"
    error: str = "#D87582"


AKIHA_PALETTE = AkihaPalette()


def settings_stylesheet() -> str:
    """Return the scoped stylesheet for the Settings window."""
    color = AKIHA_PALETTE
    root = "QWidget#akihaSettingsWindow"
    return f"""
{root} {{
    background-color: {color.window};
    color: {color.text};
    font-family: "Segoe UI";
    font-size: 13px;
}}
{root} QLabel {{
    color: {color.text};
    background: transparent;
}}
{root} QFrame#settingsSidebar {{
    background-color: {color.panel};
    border-right: 1px solid {color.border};
}}
{root} QLabel#settingsTitle {{
    color: {color.highlight};
    font-size: 20px;
    font-weight: 600;
}}
{root} QLabel#settingsVersion,
{root} QLabel#settingsSectionLabel {{
    color: {color.muted_text};
    font-family: "Cascadia Mono";
    font-size: 10px;
    font-weight: 600;
}}
{root} QLabel#settingsSectionLabel {{
    padding: 0 8px 4px 8px;
}}
{root} QPushButton#settingsNavButton {{
    min-height: 40px;
    padding: 0 12px;
    border: none;
    border-radius: 5px;
    background-color: transparent;
    color: {color.muted_text};
    font-weight: 600;
    text-align: left;
}}
{root} QPushButton#settingsNavButton:hover {{
    background-color: {color.control};
    color: {color.text};
}}
{root} QPushButton#settingsNavButton:checked {{
    background-color: {color.primary};
    color: {color.window};
}}
{root} QFrame#settingsSidebarSeparator {{
    max-height: 1px;
    border: none;
    background-color: {color.border};
}}
{root} QPushButton#sidebarUtilityButton {{
    min-height: 34px;
    padding: 0 8px;
    border: none;
    background-color: transparent;
    color: {color.muted_text};
    text-align: left;
}}
{root} QPushButton#sidebarUtilityButton:hover {{
    background-color: {color.control};
    color: {color.text};
}}
{root} QFrame#settingsMainPanel,
{root} QFrame#settingsPage {{
    border: none;
    background-color: {color.window};
}}
{root} QLabel#settingsPageTitle {{
    color: {color.text};
    font-size: 24px;
    font-weight: 600;
}}
{root} QLabel#settingsPageDescription {{
    color: {color.muted_text};
    font-size: 13px;
}}
{root} QFrame#settingsManagementBar {{
    border: none;
    border-top: 1px solid {color.border};
    background-color: {color.panel};
}}
{root} QGroupBox#settingsSection {{
    margin-top: 13px;
    padding: 20px 16px 16px 16px;
    border: 1px solid {color.border};
    border-radius: 8px;
    background-color: {color.panel};
    font-weight: 600;
}}
{root} QGroupBox#settingsSection::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 5px;
    color: {color.highlight};
    background-color: {color.window};
    font-family: "Cascadia Mono";
    font-size: 11px;
    font-weight: 600;
}}
{root} QScrollArea {{
    border: none;
    background: transparent;
}}
{root} QScrollArea > QWidget > QWidget {{
    background-color: {color.window};
}}
{root} QLineEdit,
{root} QPlainTextEdit,
{root} QComboBox,
{root} QSpinBox,
{root} QDoubleSpinBox,
{root} QTimeEdit {{
    min-height: 32px;
    padding: 0 10px;
    border: 1px solid {color.border};
    border-radius: 4px;
    background-color: {color.control};
    color: {color.text};
    selection-background-color: {color.primary};
    selection-color: {color.window};
}}
{root} QPlainTextEdit {{
    padding: 8px 9px;
}}
{root} QLineEdit:focus,
{root} QPlainTextEdit:focus,
{root} QComboBox:focus,
{root} QSpinBox:focus,
{root} QDoubleSpinBox:focus,
{root} QTimeEdit:focus {{
    border-color: {color.highlight};
}}
{root} QLineEdit:disabled,
{root} QPlainTextEdit:disabled,
{root} QComboBox:disabled,
{root} QSpinBox:disabled,
{root} QDoubleSpinBox:disabled,
{root} QTimeEdit:disabled {{
    color: #6F7488;
    background-color: #252832;
}}
{root} QComboBox::drop-down {{
    width: 30px;
    border: none;
}}
{root} QComboBox {{
    padding-right: 30px;
}}
{root} QComboBox::down-arrow {{
    width: 0;
    height: 0;
    image: none;
}}
{root} QSpinBox,
{root} QDoubleSpinBox,
{root} QTimeEdit {{
    padding-right: 30px;
}}
{root} QSpinBox::up-button,
{root} QDoubleSpinBox::up-button,
{root} QTimeEdit::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 28px;
    border: none;
    border-left: 1px solid {color.border};
    background-color: transparent;
}}
{root} QSpinBox::down-button,
{root} QDoubleSpinBox::down-button,
{root} QTimeEdit::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 28px;
    border: none;
    border-left: 1px solid {color.border};
    background-color: transparent;
}}
{root} QSpinBox::up-button:hover,
{root} QSpinBox::down-button:hover,
{root} QDoubleSpinBox::up-button:hover,
{root} QDoubleSpinBox::down-button:hover,
{root} QTimeEdit::up-button:hover,
{root} QTimeEdit::down-button:hover {{
    background-color: #343846;
}}
{root} QSpinBox::up-arrow,
{root} QSpinBox::down-arrow,
{root} QDoubleSpinBox::up-arrow,
{root} QDoubleSpinBox::down-arrow,
{root} QTimeEdit::up-arrow,
{root} QTimeEdit::down-arrow {{
    width: 0;
    height: 0;
    image: none;
}}
{root} QComboBox QAbstractItemView {{
    border: 1px solid {color.border};
    background-color: {color.control};
    color: {color.text};
    selection-background-color: {color.primary};
    selection-color: {color.window};
    outline: none;
}}
{root} QListWidget {{
    padding: 6px;
    border: 1px solid {color.border};
    border-radius: 4px;
    background-color: {color.window};
    color: {color.text};
    selection-background-color: {color.primary};
    selection-color: {color.window};
    outline: none;
}}
{root} QListWidget::item {{
    min-height: 28px;
    padding: 3px 6px;
}}
{root} QListWidget::item:hover {{
    background-color: {color.control};
}}
{root} QCheckBox {{
    spacing: 9px;
    color: {color.text};
}}
{root} QCheckBox::indicator {{
    width: 17px;
    height: 17px;
    border: 1px solid {color.border};
    border-radius: 4px;
    background-color: {color.control};
}}
{root} QCheckBox::indicator:hover {{
    border-color: {color.highlight};
}}
{root} QCheckBox::indicator:checked {{
    border-color: {color.highlight};
    background-color: {color.primary};
}}
{root} QCheckBox::indicator:disabled {{
    border-color: #343847;
    background-color: #252832;
}}
{root} QPushButton {{
    min-height: 32px;
    padding: 0 13px;
    border: 1px solid {color.border};
    border-radius: 4px;
    background-color: {color.control};
    color: {color.text};
}}
{root} QPushButton:hover {{
    border-color: {color.highlight};
    background-color: #343846;
}}
{root} QPushButton:pressed {{
    background-color: {color.panel};
}}
{root} QPushButton:disabled {{
    color: #6F7488;
    border-color: #343847;
    background-color: #252832;
}}
{root} QPushButton#primaryButton {{
    min-height: 38px;
    border-color: {color.highlight};
    background-color: {color.primary};
    color: {color.window};
    font-weight: 600;
}}
{root} QPushButton#primaryButton:hover {{
    background-color: {color.highlight};
}}
{root} QPushButton#dangerButton {{
    border-color: {color.error};
    background-color: transparent;
    color: #FFB4AB;
}}
{root} QPushButton#dangerButton:hover {{
    background-color: #3A252C;
}}
{root} QScrollBar:vertical {{
    width: 9px;
    margin: 2px;
    border: none;
    background-color: {color.window};
}}
{root} QScrollBar::handle:vertical {{
    min-height: 32px;
    border-radius: 4px;
    background-color: {color.border};
}}
{root} QScrollBar::handle:vertical:hover {{
    background-color: {color.primary};
}}
{root} QScrollBar::add-line:vertical,
{root} QScrollBar::sub-line:vertical,
{root} QScrollBar::add-page:vertical,
{root} QScrollBar::sub-page:vertical {{
    height: 0;
    background: transparent;
}}
{root} QToolTip {{
    border: 1px solid {color.border};
    padding: 5px;
    background-color: {color.control};
    color: {color.text};
}}
"""


def chat_stylesheet() -> str:
    """Return the scoped stylesheet for the Chat window."""
    color = AKIHA_PALETTE
    root = "QWidget#akihaChatWindow"
    return f"""
{root} {{
    background-color: {color.window};
    color: {color.text};
    font-family: "Segoe UI";
    font-size: 13px;
}}
{root} QLabel {{
    color: {color.text};
    background: transparent;
}}
{root} QFrame#chatToolbar,
{root} QFrame#chatComposer {{
    border: 1px solid {color.border};
    border-radius: 8px;
    background-color: {color.panel};
}}
{root} QLabel#chatPresence {{
    color: {color.highlight};
    font-weight: 600;
}}
{root} QLabel#chatStatus,
{root} QLabel#voiceInputStatus {{
    color: {color.muted_text};
}}
{root} QTextEdit#chatHistory {{
    padding: 10px;
    border: 1px solid {color.border};
    border-radius: 8px;
    background-color: {color.panel};
    color: {color.text};
    selection-background-color: {color.primary};
    selection-color: {color.window};
}}
{root} QLineEdit#chatInput {{
    min-height: 34px;
    padding: 0 10px;
    border: 1px solid {color.border};
    border-radius: 6px;
    background-color: {color.control};
    color: {color.text};
    selection-background-color: {color.primary};
    selection-color: {color.window};
}}
{root} QLineEdit#chatInput:focus {{
    border-color: {color.highlight};
}}
{root} QLineEdit#chatInput:disabled {{
    color: #6F7488;
    background-color: #252832;
}}
{root} QPushButton {{
    min-height: 32px;
    padding: 0 13px;
    border: 1px solid {color.border};
    border-radius: 6px;
    background-color: {color.control};
    color: {color.text};
}}
{root} QPushButton:hover {{
    border-color: {color.highlight};
    background-color: #343846;
}}
{root} QPushButton:pressed {{
    background-color: {color.panel};
}}
{root} QPushButton:disabled {{
    color: #6F7488;
    border-color: #343847;
    background-color: #252832;
}}
{root} QPushButton#primaryButton {{
    border-color: {color.highlight};
    background-color: {color.primary};
    color: {color.window};
    font-weight: 600;
}}
{root} QPushButton#primaryButton:hover {{
    background-color: {color.highlight};
}}
{root} QPushButton#stopButton:enabled {{
    border-color: {color.error};
    color: {color.error};
}}
{root} QPushButton#replayButton {{
    min-width: 34px;
    max-width: 34px;
    padding: 0;
}}
{root} QScrollBar:vertical {{
    width: 10px;
    margin: 2px;
    border: none;
    background-color: {color.panel};
}}
{root} QScrollBar::handle:vertical {{
    min-height: 32px;
    border-radius: 4px;
    background-color: {color.border};
}}
{root} QScrollBar::handle:vertical:hover {{
    background-color: {color.primary};
}}
{root} QScrollBar::add-line:vertical,
{root} QScrollBar::sub-line:vertical,
{root} QScrollBar::add-page:vertical,
{root} QScrollBar::sub-page:vertical {{
    height: 0;
    background: transparent;
}}
{root} QToolTip {{
    border: 1px solid {color.border};
    padding: 5px;
    background-color: {color.control};
    color: {color.text};
}}
"""


def action_history_stylesheet() -> str:
    """Return the scoped stylesheet for assistant action history."""
    return manager_window_stylesheet("akihaAssistantActionHistoryWindow")


def memory_window_stylesheet() -> str:
    """Return the scoped stylesheet for memory management."""
    return manager_window_stylesheet("akihaMemoryWindow")


def behavior_history_stylesheet() -> str:
    """Return the scoped stylesheet for behavior history."""
    return manager_window_stylesheet("akihaBehaviorHistoryWindow")


def pet_care_stylesheet() -> str:
    """Return the scoped stylesheet for the compact pet-care surface."""
    color = AKIHA_PALETTE
    root = "QWidget#akihaPetCareWindow"
    return f"""
{root} {{
    background-color: {color.window};
    color: {color.text};
    font-family: "Segoe UI";
    font-size: 13px;
}}
{root} QLabel {{
    color: {color.text};
    background: transparent;
}}
{root} QFrame#careHeader {{
    min-height: 72px;
    border: none;
    border-bottom: 1px solid {color.border};
    background-color: {color.control};
}}
{root} QFrame#careBody {{
    border: none;
    background-color: {color.window};
}}
{root} QLabel#careTitle {{
    color: {color.text};
    font-size: 18px;
    font-weight: 600;
}}
{root} QLabel#careSummary,
{root} QLabel#careMeta {{
    color: {color.muted_text};
    font-size: 12px;
}}
{root} QLabel#careLevel {{
    color: {color.highlight};
    font-size: 20px;
    font-weight: 600;
}}
{root} QLabel#careCurrency {{
    color: {color.speaking};
    font-weight: 600;
}}
{root} QLabel#careSectionTitle,
{root} QLabel#careNeedLabel {{
    color: {color.text};
    font-weight: 600;
}}
{root} QLabel#careNeedValue {{
    color: {color.speaking};
    font-family: "Cascadia Mono";
    font-weight: 600;
}}
{root} QLabel#careNotice {{
    min-height: 30px;
    color: {color.muted_text};
}}
{root} QLabel#careNotice[semantic="error"] {{
    color: {color.error};
}}
{root} QFrame#careProgressionPanel,
{root} QFrame#careNeedRow {{
    border: 1px solid {color.border};
    border-radius: 6px;
    background-color: {color.panel};
}}
{root} QProgressBar {{
    min-height: 8px;
    max-height: 8px;
    border: none;
    border-radius: 4px;
    background-color: {color.control};
}}
{root} QProgressBar::chunk {{
    border-radius: 4px;
    background-color: {color.primary};
}}
{root} QProgressBar#careXpBar::chunk {{
    background-color: {color.highlight};
}}
{root} QProgressBar#careNeedBar[semantic="low"]::chunk {{
    background-color: #D4B967;
}}
{root} QProgressBar#careNeedBar[semantic="critical"]::chunk {{
    background-color: {color.error};
}}
{root} QPushButton {{
    min-height: 34px;
    padding: 0 12px;
    border: 1px solid {color.border};
    border-radius: 5px;
    background-color: {color.control};
    color: {color.text};
}}
{root} QPushButton:hover {{
    border-color: {color.highlight};
    background-color: #353946;
}}
{root} QPushButton:pressed {{
    background-color: {color.panel};
}}
{root} QPushButton:disabled {{
    color: #6F7488;
    border-color: #343847;
    background-color: #252832;
}}
{root} QPushButton#careActionButton {{
    min-height: 40px;
}}
{root} QPushButton#careIconButton {{
    min-width: 32px;
    max-width: 32px;
    padding: 0;
    border: none;
    background-color: transparent;
}}
{root} QPushButton#careIconButton:hover {{
    background-color: {color.panel};
}}
{root} QToolTip {{
    border: 1px solid {color.border};
    padding: 5px;
    background-color: {color.control};
    color: {color.text};
}}
"""


def manager_window_stylesheet(object_name: str) -> str:
    """Return the shared technical-modal stylesheet."""
    root = f"QWidget#{object_name}"
    return f"""
{root} {{
    background-color: #1A1D24;
    color: #E8E9EE;
    font-family: "Segoe UI";
    font-size: 13px;
}}
{root} QLabel {{
    color: #E8E9EE;
    background: transparent;
}}
{root} QFrame#managerHeader {{
    min-height: 76px;
    border: none;
    border-bottom: 1px solid #3A3F52;
    background-color: #2C303C;
}}
{root} QFrame#managerFooter {{
    min-height: 54px;
    border: none;
    border-top: 1px solid #3A3F52;
    background-color: #22252E;
}}
{root} QFrame#managerFilters {{
    min-height: 56px;
    max-height: 56px;
    border: none;
    border-bottom: 1px solid #3A3F52;
    background-color: #2C303C;
}}
{root} QFrame#managerBody {{
    border: none;
    background-color: #1A1D24;
}}
{root} QFrame#managerNavigationPane {{
    border: none;
    border-right: 1px solid #3A3F52;
    background-color: #2C303C;
}}
{root} QFrame#managerDetailPane {{
    border: none;
    background-color: #1A1D24;
}}
{root} QFrame#managerDetailHeader {{
    border: none;
    border-bottom: 1px solid #3A3F52;
    background-color: #1A1D24;
}}
{root} QFrame#managerMetadataGrid {{
    border: none;
    border-bottom: 1px solid #3A3F52;
    background-color: #1A1D24;
}}
{root} QLabel#managerTitle {{
    color: #E8E9EE;
    font-size: 18px;
    font-weight: 600;
}}
{root} QLabel#managerStatus,
{root} QLabel#actionHistoryStatus {{
    color: #C7C5D1;
    font-size: 12px;
}}
{root} QLabel#managerStatusDot {{
    color: #BFC2FF;
    font-size: 10px;
}}
{root} QLabel#managerStatusDotMuted {{
    color: #918F9B;
    font-size: 10px;
}}
{root} QLabel#managerDetailTitle {{
    color: #E8E9EE;
    font-size: 18px;
    font-weight: 600;
}}
{root} QLabel#managerDetailMeta {{
    color: #C7C5D1;
    font-size: 12px;
}}
{root} QLabel#managerBadge {{
    color: #BFC2FF;
    font-family: "Cascadia Mono";
    font-size: 11px;
    font-weight: 600;
}}
{root} QLabel#managerSectionLabel,
{root} QLabel#managerFieldLabel {{
    color: #C7C5D1;
    font-size: 11px;
    font-weight: 600;
}}
{root} QLabel#managerSectionLabel {{
    padding: 14px 24px 8px 24px;
}}
{root} QLabel#managerValueChip {{
    padding: 5px 8px;
    border: 1px solid #3A3F52;
    border-radius: 3px;
    background-color: #2C303C;
    color: #E8E9EE;
    font-family: "Cascadia Mono";
    font-size: 11px;
}}
{root} QLabel#statusBadge {{
    padding: 5px 9px;
    border: 1px solid #5D6386;
    border-radius: 3px;
    background-color: #2A2E40;
    color: #BFC2FF;
    font-family: "Cascadia Mono";
    font-size: 10px;
    font-weight: 600;
}}
{root} QLabel#statusBadge[semantic="success"] {{
    border-color: #547E66;
    background-color: #21332A;
    color: #8ED1A6;
}}
{root} QLabel#statusBadge[semantic="warning"] {{
    border-color: #7E7139;
    background-color: #37321E;
    color: #E0C561;
}}
{root} QLabel#statusBadge[semantic="error"] {{
    border-color: #8A5158;
    background-color: #3A2428;
    color: #FFB4AB;
}}
{root} QTabWidget#managerTabContainer {{
    background-color: #22252E;
}}
{root} QTabWidget#managerTabContainer::pane {{
    border: none;
    background-color: #22252E;
    top: -1px;
}}
{root} QTabBar#managerTabs {{
    background-color: #22252E;
}}
{root} QTabBar::tab {{
    min-width: 92px;
    min-height: 38px;
    padding: 0 12px;
    border: none;
    border-bottom: 2px solid transparent;
    background-color: #22252E;
    color: #C7C5D1;
}}
{root} QTabBar::tab:selected {{
    border-bottom-color: #BFC2FF;
    background-color: transparent;
    color: #BFC2FF;
    font-weight: 600;
}}
{root} QTabBar::tab:hover:!selected {{
    color: #E8E9EE;
}}
{root} QLineEdit#managerSearchInput {{
    min-height: 34px;
    padding: 0 10px;
    border: 1px solid #C7C5D1;
    border-radius: 2px;
    background-color: #F7F7FA;
    color: #303035;
    selection-background-color: #878BD1;
    selection-color: #FFFFFF;
}}
{root} QLineEdit#managerSearchInput:focus {{
    border-color: #9599E0;
}}
{root} QComboBox {{
    min-height: 34px;
    padding: 0 30px 0 10px;
    border: 1px solid #3A3F52;
    border-radius: 3px;
    background-color: #2C303C;
    color: #E8E9EE;
}}
{root} QListWidget {{
    padding: 0;
    border: none;
    border-radius: 0;
    background-color: #1A1D24;
    color: #E8E9EE;
    selection-background-color: transparent;
    selection-color: #E8E9EE;
    outline: none;
}}
{root} QListWidget#memoryCardList {{
    background-color: #2C303C;
}}
{root} QListWidget#actionRecordList {{
    background-color: #2C303C;
}}
{root} QPlainTextEdit#managerCodeBlock {{
    margin: 0 24px 22px 24px;
    padding: 14px;
    border: 1px solid #3A3F52;
    border-radius: 3px;
    background-color: #0E0E12;
    color: #C7C5D1;
    font-family: "Cascadia Mono";
    font-size: 12px;
    selection-background-color: #3C4081;
    selection-color: #E8E9EE;
}}
{root} QListWidget::item {{
    border: none;
    background-color: transparent;
}}
{root} QComboBox:focus,
{root} QPlainTextEdit#managerCodeBlock:focus,
{root} QListWidget:focus {{
    border-color: #9599E0;
}}
{root} QPushButton {{
    min-height: 32px;
    padding: 0 13px;
    border: 1px solid #3A3F52;
    border-radius: 4px;
    background-color: #2C303C;
    color: #E8E9EE;
}}
{root} QPushButton:hover {{
    border-color: #9599E0;
    background-color: #353946;
}}
{root} QPushButton#primaryButton {{
    border-color: #9599E0;
    background-color: #7B7FC4;
    color: #F4F4FA;
    font-weight: 600;
}}
{root} QPushButton#dangerButton {{
    border-color: #D87582;
    color: #FFB4AB;
    background-color: transparent;
}}
{root} QPushButton#copyButton {{
    min-height: 26px;
    padding: 0 6px;
    border: none;
    background-color: transparent;
    color: #BFC2FF;
}}
{root} QPushButton#closeButton {{
    min-width: 32px;
    max-width: 32px;
    padding: 0;
    border: none;
    background-color: transparent;
}}
{root} QSplitter::handle {{
    width: 1px;
    background-color: #3A3F52;
}}
{root} QComboBox::drop-down {{
    width: 30px;
    border: none;
}}
{root} QComboBox::down-arrow {{
    width: 0;
    height: 0;
    image: none;
}}
{root} QComboBox QAbstractItemView {{
    border: 1px solid #3A3F52;
    background-color: #2C303C;
    color: #E8E9EE;
    selection-background-color: #3C4081;
    selection-color: #E8E9EE;
    outline: none;
}}
{root} QScrollBar:vertical {{
    width: 9px;
    margin: 2px;
    border: none;
    background-color: transparent;
}}
{root} QScrollBar::handle:vertical {{
    min-height: 30px;
    border-radius: 4px;
    background-color: #3A3F52;
}}
{root} QScrollBar::handle:vertical:hover {{
    background-color: #7B7FC4;
}}
{root} QScrollBar::add-line:vertical,
{root} QScrollBar::sub-line:vertical,
{root} QScrollBar::add-page:vertical,
{root} QScrollBar::sub-page:vertical {{
    height: 0;
    background: transparent;
}}
"""
