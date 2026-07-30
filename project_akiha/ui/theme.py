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
    font-size: 13px;
}}
{root} QLabel {{
    color: {color.text};
    background: transparent;
}}
{root} QTabWidget::pane {{
    border: 1px solid {color.border};
    border-radius: 8px;
    background-color: {color.window};
    top: -1px;
}}
{root} QTabBar::tab {{
    min-width: 72px;
    min-height: 36px;
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
{root} QTabBar::tab:hover:!selected {{
    background-color: {color.panel};
    color: {color.text};
}}
{root} QGroupBox#settingsSection {{
    margin-top: 13px;
    padding: 18px 14px 14px 14px;
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
    background-color: {color.panel};
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
    min-height: 30px;
    padding: 0 9px;
    border: 1px solid {color.border};
    border-radius: 5px;
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
    width: 26px;
    border: none;
}}
{root} QComboBox QAbstractItemView {{
    border: 1px solid {color.border};
    background-color: {color.control};
    color: {color.text};
    selection-background-color: {color.primary};
    selection-color: {color.window};
    outline: none;
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
{root} QScrollBar:vertical {{
    width: 10px;
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
