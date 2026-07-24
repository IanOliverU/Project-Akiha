"""Settings window for Phase 1 desktop pet options."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTime, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from project_akiha.config import (
    AIConfig,
    AppConfig,
    BehaviorConfig,
    MemoryConfig,
    PersonalityConfig,
    PetWindowConfig,
)


class SettingsWindow(QWidget):
    """Small settings surface for Phase 1 pet configuration."""

    settings_saved = Signal(object)
    position_reset_requested = Signal()
    memory_manager_requested = Signal()

    def __init__(
        self,
        config: AppConfig,
        log_dir: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._log_dir = log_dir

        self.setWindowTitle("Project Akiha Settings")
        self.setMinimumWidth(420)

        self._width_input = _build_spinbox(64, 2000, config.pet_window.width)
        self._height_input = _build_spinbox(64, 2000, config.pet_window.height)
        self._fps_input = _build_spinbox(1, 120, config.pet_window.frames_per_second)
        self._walking_speed_input = _build_spinbox(
            1,
            32,
            config.pet_window.walking_speed_pixels,
        )
        self._start_x_input = _build_spinbox(-10000, 10000, config.pet_window.start_x)
        self._start_y_input = _build_spinbox(-10000, 10000, config.pet_window.start_y)
        self._always_on_top_input = QCheckBox()
        self._always_on_top_input.setChecked(config.pet_window.always_on_top)
        self._manifest_path_input = QLineEdit(config.pet_window.animation_manifest_path)
        self._ai_provider_input = QComboBox()
        self._ai_provider_input.addItems(["mock", "ollama"])
        self._ai_provider_input.setCurrentText(config.ai.provider)
        self._ollama_base_url_input = QLineEdit(config.ai.ollama_base_url)
        self._ollama_model_input = QLineEdit(config.ai.ollama_model)
        self._ai_timeout_input = _build_spinbox(
            1,
            600,
            config.ai.request_timeout_seconds,
        )
        self._character_name_input = QLineEdit(config.personality.character_name)
        self._system_prompt_input = QPlainTextEdit(config.personality.system_prompt)
        self._system_prompt_input.setMinimumHeight(96)
        self._memory_enabled_input = QCheckBox()
        self._memory_enabled_input.setChecked(config.memory.enabled)
        self._memory_approval_input = QCheckBox()
        self._memory_approval_input.setChecked(config.memory.require_approval)
        self._memory_retrieval_limit_input = _build_spinbox(
            1,
            20,
            config.memory.retrieval_limit,
        )
        self._behavior_enabled_input = QCheckBox()
        self._behavior_enabled_input.setChecked(config.behavior.enabled)
        self._proactive_enabled_input = QCheckBox()
        self._proactive_enabled_input.setChecked(config.behavior.proactive_enabled)
        self._idle_after_input = _build_spinbox(
            30,
            86400,
            config.behavior.idle_after_seconds,
        )
        self._away_after_input = _build_spinbox(
            60,
            86400,
            config.behavior.away_after_seconds,
        )
        self._idle_after_input.valueChanged.connect(self._sync_away_minimum)
        self._sync_away_minimum(config.behavior.idle_after_seconds)
        self._notification_cooldown_input = _build_spinbox(
            60,
            86400,
            config.behavior.minimum_seconds_between_notifications,
        )
        self._allow_notifications_while_away_input = QCheckBox()
        self._allow_notifications_while_away_input.setChecked(
            config.behavior.allow_notifications_while_away
        )
        self._scheduled_check_ins_enabled_input = QCheckBox()
        self._scheduled_check_ins_enabled_input.setChecked(
            config.behavior.scheduled_check_ins_enabled
        )
        self._scheduled_check_in_interval_input = _build_spinbox(
            60,
            86400,
            config.behavior.scheduled_check_in_interval_seconds,
        )
        self._quiet_hours_enabled_input = QCheckBox()
        self._quiet_hours_enabled_input.setChecked(config.behavior.quiet_hours_enabled)
        self._quiet_hours_start_input = _build_time_input(
            config.behavior.quiet_hours_start
        )
        self._quiet_hours_end_input = _build_time_input(config.behavior.quiet_hours_end)

        form_layout = QFormLayout()
        form_layout.addRow("Width", self._width_input)
        form_layout.addRow("Height", self._height_input)
        form_layout.addRow("FPS", self._fps_input)
        form_layout.addRow("Walking speed", self._walking_speed_input)
        form_layout.addRow("Start X", self._start_x_input)
        form_layout.addRow("Start Y", self._start_y_input)
        form_layout.addRow("Always on top", self._always_on_top_input)
        form_layout.addRow("Animation manifest", self._build_manifest_row())
        form_layout.addRow("AI provider", self._ai_provider_input)
        form_layout.addRow("Ollama URL", self._ollama_base_url_input)
        form_layout.addRow("Ollama model", self._ollama_model_input)
        form_layout.addRow("AI timeout", self._ai_timeout_input)
        form_layout.addRow("Companion name", self._character_name_input)
        form_layout.addRow("System prompt", self._system_prompt_input)
        form_layout.addRow("Memory enabled", self._memory_enabled_input)
        form_layout.addRow("Approve memories", self._memory_approval_input)
        form_layout.addRow("Memory retrieval limit", self._memory_retrieval_limit_input)
        form_layout.addRow("Behavior enabled", self._behavior_enabled_input)
        form_layout.addRow("Proactive enabled", self._proactive_enabled_input)
        form_layout.addRow("Idle after seconds", self._idle_after_input)
        form_layout.addRow("Away after seconds", self._away_after_input)
        form_layout.addRow("Notification cooldown", self._notification_cooldown_input)
        form_layout.addRow(
            "Notify while away",
            self._allow_notifications_while_away_input,
        )
        form_layout.addRow(
            "Scheduled check-ins",
            self._scheduled_check_ins_enabled_input,
        )
        form_layout.addRow(
            "Check-in interval",
            self._scheduled_check_in_interval_input,
        )
        form_layout.addRow("Quiet hours enabled", self._quiet_hours_enabled_input)
        form_layout.addRow("Quiet hours start", self._quiet_hours_start_input)
        form_layout.addRow("Quiet hours end", self._quiet_hours_end_input)

        save_button = QPushButton("Save")
        save_button.clicked.connect(self._save)

        reset_position_button = QPushButton("Reset position")
        reset_position_button.clicked.connect(self.position_reset_requested.emit)

        open_logs_button = QPushButton("Open logs")
        open_logs_button.clicked.connect(self._open_logs)

        memories_button = QPushButton("Memories")
        memories_button.clicked.connect(self.memory_manager_requested.emit)

        button_layout = QHBoxLayout()
        button_layout.addWidget(save_button)
        button_layout.addWidget(reset_position_button)
        button_layout.addWidget(open_logs_button)
        button_layout.addWidget(memories_button)

        form_container = QWidget()
        form_container.setLayout(form_layout)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(form_container)

        layout = QVBoxLayout()
        layout.addWidget(scroll_area)
        layout.addLayout(button_layout)
        self.setLayout(layout)

    def update_config(self, config: AppConfig) -> None:
        """Refresh controls from the current config."""
        self._config = config
        self._width_input.setValue(config.pet_window.width)
        self._height_input.setValue(config.pet_window.height)
        self._fps_input.setValue(config.pet_window.frames_per_second)
        self._walking_speed_input.setValue(config.pet_window.walking_speed_pixels)
        self._start_x_input.setValue(config.pet_window.start_x)
        self._start_y_input.setValue(config.pet_window.start_y)
        self._always_on_top_input.setChecked(config.pet_window.always_on_top)
        self._manifest_path_input.setText(config.pet_window.animation_manifest_path)
        self._ai_provider_input.setCurrentText(config.ai.provider)
        self._ollama_base_url_input.setText(config.ai.ollama_base_url)
        self._ollama_model_input.setText(config.ai.ollama_model)
        self._ai_timeout_input.setValue(config.ai.request_timeout_seconds)
        self._character_name_input.setText(config.personality.character_name)
        self._system_prompt_input.setPlainText(config.personality.system_prompt)
        self._memory_enabled_input.setChecked(config.memory.enabled)
        self._memory_approval_input.setChecked(config.memory.require_approval)
        self._memory_retrieval_limit_input.setValue(config.memory.retrieval_limit)
        self._behavior_enabled_input.setChecked(config.behavior.enabled)
        self._proactive_enabled_input.setChecked(config.behavior.proactive_enabled)
        self._idle_after_input.setValue(config.behavior.idle_after_seconds)
        self._sync_away_minimum(config.behavior.idle_after_seconds)
        self._away_after_input.setValue(config.behavior.away_after_seconds)
        self._notification_cooldown_input.setValue(
            config.behavior.minimum_seconds_between_notifications
        )
        self._allow_notifications_while_away_input.setChecked(
            config.behavior.allow_notifications_while_away
        )
        self._scheduled_check_ins_enabled_input.setChecked(
            config.behavior.scheduled_check_ins_enabled
        )
        self._scheduled_check_in_interval_input.setValue(
            config.behavior.scheduled_check_in_interval_seconds
        )
        self._quiet_hours_enabled_input.setChecked(config.behavior.quiet_hours_enabled)
        self._quiet_hours_start_input.setTime(
            _parse_qtime(config.behavior.quiet_hours_start)
        )
        self._quiet_hours_end_input.setTime(
            _parse_qtime(config.behavior.quiet_hours_end)
        )

    def _build_manifest_row(self) -> QWidget:
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._browse_manifest)

        row = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._manifest_path_input)
        layout.addWidget(browse_button)
        row.setLayout(layout)
        return row

    def _browse_manifest(self) -> None:
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select animation manifest",
            self._manifest_path_input.text(),
            "TOML files (*.toml);;All files (*)",
        )
        if selected_path:
            self._manifest_path_input.setText(selected_path)

    def _save(self) -> None:
        pet_window = PetWindowConfig(
            width=self._width_input.value(),
            height=self._height_input.value(),
            frames_per_second=self._fps_input.value(),
            walking_speed_pixels=self._walking_speed_input.value(),
            start_x=self._start_x_input.value(),
            start_y=self._start_y_input.value(),
            always_on_top=self._always_on_top_input.isChecked(),
            animation_manifest_path=self._manifest_path_input.text(),
        )
        config = self._config.with_pet_window(pet_window)
        config = config.with_ai(
            AIConfig(
                provider=self._ai_provider_input.currentText(),
                ollama_base_url=self._ollama_base_url_input.text(),
                ollama_model=self._ollama_model_input.text(),
                request_timeout_seconds=self._ai_timeout_input.value(),
            )
        )
        config = config.with_personality(
            PersonalityConfig(
                character_name=self._character_name_input.text(),
                system_prompt=self._system_prompt_input.toPlainText(),
            )
        )
        config = config.with_memory(
            MemoryConfig(
                enabled=self._memory_enabled_input.isChecked(),
                retrieval_limit=self._memory_retrieval_limit_input.value(),
                require_approval=self._memory_approval_input.isChecked(),
            )
        )
        config = config.with_behavior(
            BehaviorConfig(
                enabled=self._behavior_enabled_input.isChecked(),
                proactive_enabled=self._proactive_enabled_input.isChecked(),
                idle_after_seconds=self._idle_after_input.value(),
                away_after_seconds=self._away_after_input.value(),
                minimum_seconds_between_notifications=(
                    self._notification_cooldown_input.value()
                ),
                allow_notifications_while_away=(
                    self._allow_notifications_while_away_input.isChecked()
                ),
                scheduled_check_ins_enabled=(
                    self._scheduled_check_ins_enabled_input.isChecked()
                ),
                scheduled_check_in_interval_seconds=(
                    self._scheduled_check_in_interval_input.value()
                ),
                quiet_hours_enabled=self._quiet_hours_enabled_input.isChecked(),
                quiet_hours_start=_format_time_input(self._quiet_hours_start_input),
                quiet_hours_end=_format_time_input(self._quiet_hours_end_input),
            )
        )
        self.update_config(config)
        self.settings_saved.emit(config)

    def _sync_away_minimum(self, idle_after_seconds: int) -> None:
        self._away_after_input.setMinimum(idle_after_seconds + 1)

    def _open_logs(self) -> None:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._log_dir)))


def _build_spinbox(minimum: int, maximum: int, value: int) -> QSpinBox:
    spinbox = QSpinBox()
    spinbox.setRange(minimum, maximum)
    spinbox.setValue(value)
    return spinbox


def _build_time_input(value: str) -> QTimeEdit:
    time_input = QTimeEdit()
    time_input.setDisplayFormat("HH:mm")
    time_input.setTime(_parse_qtime(value))
    return time_input


def _parse_qtime(value: str) -> QTime:
    hour, minute = value.split(":", maxsplit=1)
    return QTime(int(hour), int(minute))


def _format_time_input(time_input: QTimeEdit) -> str:
    return time_input.time().toString("HH:mm")
