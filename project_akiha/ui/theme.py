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
    color = AKIHA_PALETTE
    root = "QWidget#akihaAssistantActionHistoryWindow"
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
{root} QLabel#actionHistoryStatus {{
    color: {color.highlight};
    font-weight: 600;
}}
{root} QTabWidget::pane {{
    border: 1px solid {color.border};
    border-radius: 8px;
    background-color: {color.window};
}}
{root} QTabBar::tab {{
    min-width: 108px;
    min-height: 34px;
    padding: 0 12px;
    margin-right: 2px;
    border: none;
    border-radius: 6px 6px 0 0;
    background: transparent;
    color: {color.muted_text};
}}
{root} QTabBar::tab:selected {{
    background-color: {color.primary};
    color: {color.window};
    font-weight: 600;
}}
{root} QLineEdit,
{root} QComboBox,
{root} QPlainTextEdit,
{root} QListWidget {{
    min-height: 30px;
    padding: 7px 9px;
    border: 1px solid {color.border};
    border-radius: 6px;
    background-color: {color.panel};
    color: {color.text};
    selection-background-color: {color.primary};
    selection-color: {color.window};
}}
{root} QPlainTextEdit {{
    padding: 10px;
}}
{root} QLineEdit:focus,
{root} QComboBox:focus,
{root} QPlainTextEdit:focus,
{root} QListWidget:focus {{
    border-color: {color.highlight};
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
{root} QSplitter::handle {{
    background-color: {color.border};
}}
{root} QComboBox::drop-down {{
    width: 26px;
    border: none;
}}
"""
