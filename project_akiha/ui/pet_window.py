"""Transparent desktop pet window for Phase 1."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QContextMenuEvent, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QMenu, QWidget

from project_akiha.config import PetWindowConfig
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.animation import AnimationState
from project_akiha.providers.animation import AnimationProvider
from project_akiha.ui.pet_renderer import PetRenderer


class PetWindow(QWidget):
    """Always-on-top draggable pet window with a simple idle animation."""

    def __init__(
        self,
        event_bus: EventBus,
        config: PetWindowConfig,
        animation_provider: AnimationProvider,
        renderer: PetRenderer,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._event_bus = event_bus
        self._config = config
        self._animation_provider = animation_provider
        self._renderer = renderer
        self._current_state = AnimationState.IDLE
        self._drag_offset: QPoint | None = None
        self._frame_number = 0

        self.setWindowTitle("Project Akiha")
        self.setFixedSize(config.width, config.height)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(self._build_window_flags(config))

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_frame)
        self._timer.start(1000 // config.frames_per_second)
        self._event_bus.subscribe(EventType.STATE_CHANGED, self._handle_state_changed)

    def apply_config(self, config: PetWindowConfig) -> None:
        """Apply runtime-safe pet window settings."""
        was_visible = self.isVisible()
        self._config = config
        self.setFixedSize(config.width, config.height)
        self._timer.setInterval(1000 // config.frames_per_second)
        self.setWindowFlags(self._build_window_flags(config))
        if was_visible:
            self.show()

    def set_animation_provider(self, animation_provider: AnimationProvider) -> None:
        """Replace the animation frame provider."""
        self._animation_provider = animation_provider
        self.update()

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

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """Open the pet action menu."""
        menu = QMenu(self)

        if self._current_state == AnimationState.SLEEPING:
            wake_action = QAction("Wake", menu)
            wake_action.triggered.connect(self._request_wake)
            menu.addAction(wake_action)
        else:
            sleep_action = QAction("Sleep", menu)
            sleep_action.triggered.connect(self._request_sleep)
            menu.addAction(sleep_action)

        menu.addSeparator()

        hide_action = QAction("Hide", menu)
        hide_action.triggered.connect(self.hide)
        menu.addAction(hide_action)

        menu.exec(event.globalPos())
        event.accept()

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the temporary Phase 1 pet placeholder."""
        del event

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        animation_frame = self._animation_provider.frame_for(
            state=self._current_state,
            frame_number=self._frame_number,
        )
        self._renderer.paint(painter, animation_frame)

    def _advance_frame(self) -> None:
        self._frame_number += 1
        self.update()

    def _build_window_flags(self, config: PetWindowConfig) -> Qt.WindowType:
        window_flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if config.always_on_top:
            window_flags |= Qt.WindowType.WindowStaysOnTopHint
        return window_flags

    def _request_sleep(self) -> None:
        self._event_bus.publish(EventType.PET_SLEEP_REQUESTED)

    def _request_wake(self) -> None:
        self._event_bus.publish(EventType.PET_WAKE_REQUESTED)

    def _handle_state_changed(self, event: Event) -> None:
        state = event.payload.get("state")
        if isinstance(state, str):
            try:
                self._current_state = AnimationState(state)
            except ValueError:
                return
            else:
                self.update()
