"""Transparent desktop pet window for Phase 1."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget

from project_akiha.config import PetWindowConfig
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.animation import AnimationState


class PetWindow(QWidget):
    """Always-on-top draggable pet window with a simple idle animation."""

    def __init__(
        self,
        event_bus: EventBus,
        config: PetWindowConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._event_bus = event_bus
        self._config = config
        self._current_state = AnimationState.IDLE
        self._drag_offset: QPoint | None = None
        self._frame = 0

        self.setWindowTitle("Project Akiha")
        self.setFixedSize(config.width, config.height)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        window_flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if config.always_on_top:
            window_flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(window_flags)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_frame)
        self._timer.start(1000 // config.frames_per_second)
        self._event_bus.subscribe(EventType.STATE_CHANGED, self._handle_state_changed)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Start dragging the pet window."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            self._event_bus.publish(EventType.PET_DRAG_STARTED)
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Move the window while dragging."""
        if self._drag_offset is not None:
            position = event.globalPosition().toPoint() - self._drag_offset
            self.move(position)
            self._event_bus.publish(
                EventType.PET_DRAGGED,
                {"x": position.x(), "y": position.y()},
            )
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """End dragging the pet window."""
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._drag_offset is not None
        ):
            self._drag_offset = None
            position = self.pos()
            self._event_bus.publish(
                EventType.PET_DRAG_ENDED,
                {"x": position.x(), "y": position.y()},
            )
            event.accept()

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the temporary Phase 1 pet placeholder."""
        del event

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bob = 4 if self._current_state == AnimationState.IDLE else 0
        y_offset = bob if self._frame % 24 < 12 else 0

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

    def _advance_frame(self) -> None:
        self._frame = (self._frame + 1) % 240
        self.update()

    def _handle_state_changed(self, event: Event) -> None:
        state = event.payload.get("state")
        if isinstance(state, str):
            try:
                self._current_state = AnimationState(state)
            except ValueError:
                return
            else:
                self.update()
