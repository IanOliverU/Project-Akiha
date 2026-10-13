"""Windows Fluent icon helpers shared by Akiha's native UI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPaintEvent, QPixmap, QPolygonF
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QComboBox

from project_akiha.ui.theme import AKIHA_PALETTE

_GLYPH_NAMES = {
    "\ue716": "pet",
    "\ue99a": "chat",
    "\ue70c": "memory",
    "\ueb51": "history",
    "\ue945": "shield",
    "\ue8d6": "music",
    "\ue787": "timer",
    "\ue713": "settings",
    "\ue720": "voice",
    "\ue8b7": "folder",
    "\ue8a5": "history",
    "\ue74e": "save",
    "\ue72c": "refresh",
    "\ue721": "search",
    "\ue8bb": "close",
    "\ue7f4": "notification",
    "\ue9d9": "pet",
    "\ue70f": "edit",
    "\ue74d": "trash",
    "\ue73e": "check",
    "\ue711": "close",
    "\ue7b8": "folder",
    "\ue777": "refresh",
    "\ue895": "memory",
    "\ue70d": "down",
    "\ue70e": "up",
    "\ue774": "link",
    "\ue8f1": "shop",
}


def fluent_icon(
    glyph: str,
    size: int = 18,
    *,
    default_color: str | None = None,
    selected_color: str | None = None,
) -> QIcon:
    """Render original bundled vector icons; legacy IDs keep bindings stable."""

    def render(color: str) -> QPixmap:
        canvas_size = size + 6
        app = QApplication.instance()
        ratio = app.devicePixelRatio() if app is not None else 1.0
        pixmap = QPixmap(round(canvas_size * ratio), round(canvas_size * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        name = _GLYPH_NAMES.get(glyph, glyph)
        if name not in {
            "chat",
            "settings",
            "memory",
            "music",
            "timer",
            "notification",
            "history",
            "pet",
            "folder",
            "shield",
            "search",
            "refresh",
            "close",
            "save",
            "voice",
            "link",
            "down",
            "up",
            "trash",
            "check",
            "edit",
            "exit",
            "shop",
            "info",
        }:
            name = "info"
        data = (
            Path(__file__).resolve().parents[2]
            / "assets"
            / "ui"
            / "icons"
            / (name + ".svg")
        ).read_bytes()
        renderer = QSvgRenderer(
            QByteArray(data.replace(b"currentColor", color.encode("ascii")))
        )
        renderer.render(painter, QRectF(3, 3, size, size))
        painter.end()
        return pixmap

    normal = default_color or AKIHA_PALETTE.muted_text
    selected = selected_color or AKIHA_PALETTE.highlight
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
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(
            QColor(AKIHA_PALETTE.muted_text if self.isEnabled() else "#6F7488")
        )
        x, y = self.width() - 18, self.height() / 2
        painter.drawPolyline(
            QPolygonF([QPointF(x - 4, y - 2), QPointF(x, y + 2), QPointF(x + 4, y - 2)])
        )
