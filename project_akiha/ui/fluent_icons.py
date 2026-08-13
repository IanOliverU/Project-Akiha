"""Windows Fluent icon helpers shared by Akiha's native UI."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPaintEvent, QPixmap
from PySide6.QtWidgets import QComboBox

from project_akiha.ui.theme import AKIHA_PALETTE


def fluent_icon(
    glyph: str,
    size: int = 18,
    *,
    default_color: str | None = None,
    selected_color: str | None = None,
) -> QIcon:
    """Render a Windows Fluent glyph with deterministic button states."""

    def render(color: str) -> QPixmap:
        canvas_size = size + 6
        pixmap = QPixmap(canvas_size, canvas_size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        font = QFont("Segoe Fluent Icons")
        font.setPixelSize(size)
        painter.setFont(font)
        painter.setPen(QColor(color))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, glyph)
        painter.end()
        return pixmap

    normal = default_color or AKIHA_PALETTE.muted_text
    selected = selected_color or AKIHA_PALETTE.window
    icon = QIcon()
    icon.addPixmap(render(normal), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(render(AKIHA_PALETTE.text), QIcon.Mode.Active, QIcon.State.Off)
    icon.addPixmap(render("#6F7488"), QIcon.Mode.Disabled, QIcon.State.Off)
    icon.addPixmap(render(selected), QIcon.Mode.Normal, QIcon.State.On)
    icon.addPixmap(render(selected), QIcon.Mode.Active, QIcon.State.On)
    icon.addPixmap(render("#6F7488"), QIcon.Mode.Disabled, QIcon.State.On)
    return icon


class FluentComboBox(QComboBox):
    """Combo box with an explicit monochrome dropdown affordance."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("fluentComboBox")

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        font = QFont("Segoe Fluent Icons")
        font.setPixelSize(12)
        painter.setFont(font)
        painter.setPen(
            QColor(AKIHA_PALETTE.muted_text if self.isEnabled() else "#6F7488")
        )
        painter.drawText(
            QRectF(self.width() - 30.0, 0.0, 24.0, float(self.height())),
            Qt.AlignmentFlag.AlignCenter,
            "\ue70d",
        )
