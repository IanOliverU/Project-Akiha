"""Settings window for Phase 1 desktop pet options."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Signal
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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from project_akiha.config import (
    AIConfig,
    AppConfig,
    MemoryConfig,
    PersonalityConfig,
    PetWindowConfig,
)


class SettingsWindow(QWidget):
    """Small settings surface for Phase 1 pet configuration."""

    settings_saved = Signal(object)
    position_reset_requested = Signal()

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
        self._memory_retrieval_limit_input = _build_spinbox(
            1,
            20,
            config.memory.retrieval_limit,
        )

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
        form_layout.addRow("Memory retrieval limit", self._memory_retrieval_limit_input)

        save_button = QPushButton("Save")
        save_button.clicked.connect(self._save)

        reset_position_button = QPushButton("Reset position")
        reset_position_button.clicked.connect(self.position_reset_requested.emit)

        open_logs_button = QPushButton("Open logs")
        open_logs_button.clicked.connect(self._open_logs)

        button_layout = QHBoxLayout()
        button_layout.addWidget(save_button)
        button_layout.addWidget(reset_position_button)
        button_layout.addWidget(open_logs_button)

        layout = QVBoxLayout()
        layout.addLayout(form_layout)
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
        self._memory_retrieval_limit_input.setValue(config.memory.retrieval_limit)

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
            )
        )
        self.update_config(config)
        self.settings_saved.emit(config)

    def _open_logs(self) -> None:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._log_dir)))


def _build_spinbox(minimum: int, maximum: int, value: int) -> QSpinBox:
    spinbox = QSpinBox()
    spinbox.setRange(minimum, maximum)
    spinbox.setValue(value)
    return spinbox
