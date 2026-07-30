"""Transparent desktop pet window for Phase 1."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QColor,
    QContextMenuEvent,
    QFont,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QMenu, QWidget

from project_akiha.config import PetWindowConfig
from project_akiha.core.behavior import (
    CompanionMood,
    MoodVisualCue,
    MoodVisualCueMapper,
)
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.animation import AnimationState
from project_akiha.providers.animation import AnimationProvider
from project_akiha.providers.animation.base import AnimationFrame
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
        self._walk_direction = 1
        self._current_mood = CompanionMood.CALM
        self._mood_visual_mapper = MoodVisualCueMapper()

        self.setWindowTitle("Project Akiha")
        self.setFixedSize(config.width, config.height)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(self._build_window_flags(config))

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_frame)
        self._timer.start(1000 // config.frames_per_second)
        self._event_bus.subscribe(EventType.STATE_CHANGED, self._handle_state_changed)
        self._event_bus.subscribe(
            EventType.MOOD_STATE_CHANGED,
            self._handle_mood_changed,
        )

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
        menu = self._build_context_menu()
        menu.exec(event.globalPos())
        event.accept()

    def _build_context_menu(self) -> QMenu:
        """Build the pet action menu."""
        menu = QMenu(self)

        if self._current_state == AnimationState.SLEEPING:
            wake_action = QAction("Wake", menu)
            wake_action.triggered.connect(self._request_wake)
            menu.addAction(wake_action)
        elif self._current_state == AnimationState.WALKING:
            stop_action = QAction("Stop walking", menu)
            stop_action.triggered.connect(self._request_idle)
            menu.addAction(stop_action)

            sleep_action = QAction("Sleep", menu)
            sleep_action.triggered.connect(self._request_sleep)
            menu.addAction(sleep_action)
        else:
            walk_action = QAction("Walk", menu)
            walk_action.triggered.connect(self._request_walk)
            menu.addAction(walk_action)

            sleep_action = QAction("Sleep", menu)
            sleep_action.triggered.connect(self._request_sleep)
            menu.addAction(sleep_action)

        menu.addSeparator()

        chat_action = QAction("Chat", menu)
        chat_action.triggered.connect(self._request_chat)
        menu.addAction(chat_action)

        settings_action = QAction("Settings", menu)
        settings_action.triggered.connect(self._request_settings)
        menu.addAction(settings_action)

        behavior_history_action = QAction("Behavior history", menu)
        behavior_history_action.triggered.connect(self._request_behavior_history)
        menu.addAction(behavior_history_action)

        hide_action = QAction("Hide", menu)
        hide_action.triggered.connect(self.hide)
        menu.addAction(hide_action)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._request_quit)
        menu.addAction(quit_action)

        return menu

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the temporary Phase 1 pet placeholder."""
        del event

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        animation_frame = self._animation_frame_for_current_state()
        self._renderer.paint(painter, animation_frame)
        self._paint_mood_visual(painter, self._mood_visual_cue_for_current_mood())

    def _animation_frame_for_current_state(self) -> AnimationFrame:
        animation_frame = self._animation_provider.frame_for(
            state=self._current_state,
            frame_number=self._frame_number,
        )
        if self._current_state == AnimationState.WALKING and self._walk_direction < 0:
            return replace(animation_frame, mirrored_horizontally=True)
        return animation_frame

    def _advance_frame(self) -> None:
        self._frame_number += 1
        if self._current_state == AnimationState.WALKING:
            self._advance_walking_position()
        self.update()

    def _advance_walking_position(self) -> None:
        screen = self.screen()
        if screen is None:
            return

        geometry = screen.availableGeometry()
        next_x = self.x() + self._config.walking_speed_pixels * self._walk_direction
        min_x = geometry.x()
        max_x = max(min_x, geometry.right() - self.width())

        if next_x <= min_x:
            next_x = min_x
            self._walk_direction = 1
        elif next_x >= max_x:
            next_x = max_x
            self._walk_direction = -1

        self.move(next_x, self.y())

    def _build_window_flags(self, config: PetWindowConfig) -> Qt.WindowType:
        window_flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if config.always_on_top:
            window_flags |= Qt.WindowType.WindowStaysOnTopHint
        return window_flags

    def _request_sleep(self) -> None:
        self._event_bus.publish(EventType.PET_SLEEP_REQUESTED)

    def _request_wake(self) -> None:
        self._event_bus.publish(EventType.PET_WAKE_REQUESTED)

    def _request_walk(self) -> None:
        self._event_bus.publish(EventType.PET_WALK_REQUESTED)

    def _request_idle(self) -> None:
        self._event_bus.publish(EventType.PET_IDLE_REQUESTED)

    def _request_settings(self) -> None:
        self._event_bus.publish(EventType.SETTINGS_OPEN_REQUESTED)

    def _request_chat(self) -> None:
        self._event_bus.publish(EventType.CHAT_OPEN_REQUESTED)

    def _request_behavior_history(self) -> None:
        self._event_bus.publish(EventType.BEHAVIOR_HISTORY_OPEN_REQUESTED)

    def _request_quit(self) -> None:
        self._event_bus.publish(EventType.APP_QUIT_REQUESTED)

    def _handle_state_changed(self, event: Event) -> None:
        state = event.payload.get("state")
        if isinstance(state, str):
            try:
                self._current_state = AnimationState(state)
            except ValueError:
                return
            else:
                self.update()

    def _handle_mood_changed(self, event: Event) -> None:
        mood = event.payload.get("mood")
        if not isinstance(mood, str):
            return

        try:
            self._current_mood = CompanionMood(mood)
        except ValueError:
            return

        self.update()

    def _mood_visual_cue_for_current_mood(self) -> MoodVisualCue:
        return self._mood_visual_mapper.cue_for(self._current_mood)

    def _paint_mood_visual(self, painter: QPainter, cue: MoodVisualCue) -> None:
        if cue == MoodVisualCue.NONE:
            return

        bubble_rect = QRectF(max(8, self.width() - 58), 10, 44, 32)
        color = _mood_visual_color(cue)

        painter.save()
        painter.setBrush(QColor(color.red(), color.green(), color.blue(), 180))
        painter.setPen(QPen(QColor(44, 28, 36, 150), 2))
        painter.drawRoundedRect(bubble_rect, 12, 12)

        painter.setPen(QPen(QColor(44, 28, 36), 2))
        if cue == MoodVisualCue.ATTENTION:
            painter.drawEllipse(
                QRectF(bubble_rect.x() + 13, bubble_rect.y() + 8, 18, 18)
            )
            painter.drawEllipse(
                QRectF(bubble_rect.x() + 18, bubble_rect.y() + 13, 8, 8)
            )
        elif cue == MoodVisualCue.WAITING:
            for offset in (10, 20, 30):
                painter.drawEllipse(
                    QRectF(bubble_rect.x() + offset, bubble_rect.y() + 15, 4, 4)
                )
        elif cue == MoodVisualCue.CHECKING_IN:
            painter.drawRoundedRect(
                QRectF(bubble_rect.x() + 10, bubble_rect.y() + 9, 24, 14),
                5,
                5,
            )
            painter.drawLine(
                int(bubble_rect.x() + 18),
                int(bubble_rect.y() + 23),
                int(bubble_rect.x() + 15),
                int(bubble_rect.y() + 28),
            )
        elif cue in {MoodVisualCue.RESTING, MoodVisualCue.SLEEPY}:
            font = QFont()
            font.setBold(True)
            font.setPointSize(10 if cue == MoodVisualCue.RESTING else 12)
            painter.setFont(font)
            text = "..." if cue == MoodVisualCue.RESTING else "Zz"
            painter.drawText(bubble_rect, Qt.AlignmentFlag.AlignCenter, text)
        elif cue == MoodVisualCue.VOICE_LISTENING:
            painter.drawEllipse(
                QRectF(bubble_rect.x() + 16, bubble_rect.y() + 8, 12, 16)
            )
            painter.drawArc(
                QRectF(bubble_rect.x() + 12, bubble_rect.y() + 7, 20, 21),
                200 * 16,
                140 * 16,
            )
            painter.drawLine(
                int(bubble_rect.center().x()),
                int(bubble_rect.y() + 25),
                int(bubble_rect.center().x()),
                int(bubble_rect.y() + 29),
            )
        elif cue == MoodVisualCue.VOICE_THINKING:
            for offset in (10, 20, 30):
                painter.drawEllipse(
                    QRectF(bubble_rect.x() + offset, bubble_rect.y() + 15, 4, 4)
                )
        elif cue == MoodVisualCue.VOICE_SPEAKING:
            painter.drawRoundedRect(
                QRectF(bubble_rect.x() + 9, bubble_rect.y() + 8, 26, 15),
                5,
                5,
            )
            for offset in (15, 22, 29):
                painter.drawPoint(
                    int(bubble_rect.x() + offset),
                    int(bubble_rect.y() + 15),
                )
        elif cue == MoodVisualCue.VOICE_MUTED:
            painter.drawEllipse(
                QRectF(bubble_rect.x() + 12, bubble_rect.y() + 9, 20, 14)
            )
            painter.drawLine(
                int(bubble_rect.x() + 10),
                int(bubble_rect.y() + 7),
                int(bubble_rect.x() + 34),
                int(bubble_rect.y() + 25),
            )
        elif cue == MoodVisualCue.VOICE_ERROR:
            font = QFont()
            font.setBold(True)
            font.setPointSize(13)
            painter.setFont(font)
            painter.drawText(bubble_rect, Qt.AlignmentFlag.AlignCenter, "!")

        painter.restore()


def _mood_visual_color(cue: MoodVisualCue) -> QColor:
    colors = {
        MoodVisualCue.ATTENTION: QColor(144, 202, 249),
        MoodVisualCue.WAITING: QColor(255, 224, 130),
        MoodVisualCue.RESTING: QColor(179, 157, 219),
        MoodVisualCue.CHECKING_IN: QColor(255, 171, 145),
        MoodVisualCue.SLEEPY: QColor(159, 168, 218),
        MoodVisualCue.VOICE_LISTENING: QColor(128, 203, 196),
        MoodVisualCue.VOICE_THINKING: QColor(255, 213, 79),
        MoodVisualCue.VOICE_SPEAKING: QColor(129, 212, 250),
        MoodVisualCue.VOICE_MUTED: QColor(189, 189, 189),
        MoodVisualCue.VOICE_ERROR: QColor(239, 154, 154),
    }
    return colors[cue]
