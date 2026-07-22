"""Qt renderers for pet animation frames."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap

from project_akiha.providers.animation.base import AnimationFrame


class PetRenderer(Protocol):
    """Paint a pet animation frame onto a Qt painter."""

    def paint(self, painter: QPainter, frame: AnimationFrame) -> None:
        """Paint the frame."""


class PlaceholderPetRenderer:
    """Paint the temporary Phase 1 pet placeholder."""

    def paint(self, painter: QPainter, frame: AnimationFrame) -> None:
        """Paint a simple pet shape for the current animation frame."""
        y_offset = frame.y_offset

        shadow = QColor(28, 28, 34, 70)
        painter.setBrush(shadow)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(42, 188, 96, 18))

        body_color = QColor(147, 42, 68)
        accent_color = QColor(252, 232, 226)
        outline_color = QColor(44, 28, 36)

        painter.setBrush(body_color)
        painter.setPen(QPen(outline_color, 3))
        painter.drawRoundedRect(QRectF(44, 62 + y_offset, 92, 128), 36, 36)

        painter.setBrush(accent_color)
        painter.drawEllipse(QRectF(58, 82 + y_offset, 22, 20))
        painter.drawEllipse(QRectF(100, 82 + y_offset, 22, 20))

        painter.setBrush(outline_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(66, 90 + y_offset, 7, 7))
        painter.drawEllipse(QRectF(108, 90 + y_offset, 7, 7))

        painter.setPen(QPen(outline_color, 3))
        painter.drawArc(QRectF(78, 110 + y_offset, 24, 16), 200 * 16, 140 * 16)

        painter.setBrush(QColor(90, 32, 48))
        painter.setPen(QPen(outline_color, 3))
        painter.drawEllipse(QRectF(58, 34 + y_offset, 24, 42))
        painter.drawEllipse(QRectF(98, 34 + y_offset, 24, 42))


class SpritePetRenderer:
    """Paint image-backed animation frames with a placeholder fallback."""

    def __init__(self, fallback_renderer: PetRenderer) -> None:
        self._fallback_renderer = fallback_renderer
        self._pixmap_cache: dict[Path, QPixmap] = {}

    def paint(self, painter: QPainter, frame: AnimationFrame) -> None:
        """Paint the frame image, or fall back when no usable image exists."""
        if frame.image_path is None:
            self._fallback_renderer.paint(painter, frame)
            return

        pixmap = self._load_pixmap(frame.image_path)
        if pixmap.isNull():
            self._fallback_renderer.paint(painter, frame)
            return

        target_rect = QRectF(painter.viewport())
        image_rect = QRectF(pixmap.rect())
        image_rect.moveCenter(target_rect.center())
        painter.drawPixmap(image_rect.toRect(), pixmap)

    def _load_pixmap(self, image_path: Path) -> QPixmap:
        cached_pixmap = self._pixmap_cache.get(image_path)
        if cached_pixmap is not None:
            return cached_pixmap

        pixmap = QPixmap(str(image_path))
        self._pixmap_cache[image_path] = pixmap
        return pixmap
