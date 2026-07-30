"""Settings window for Project Akiha configuration."""

from __future__ import annotations

from math import ceil
from pathlib import Path

from PySide6.QtCore import QTime, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from project_akiha.config import (
    AI_PROVIDERS,
    HOSTED_AI_PROVIDERS,
    AIConfig,
    AppConfig,
    BehaviorConfig,
    MemoryConfig,
    PersonalityConfig,
    PetWindowConfig,
    VoiceConfig,
)
from project_akiha.services.ai_provider_discovery import (
    AIProviderDiscoveryRequest,
    AIProviderDiscoveryResult,
)
from project_akiha.services.credential_store import (
    CredentialStore,
    CredentialStoreError,
)
from project_akiha.ui.ai_provider_discovery_worker import (
    AIProviderDiscoveryThread,
)

_AI_PROVIDER_ORDER = (
    "mock",
    "ollama",
    "gemini",
    "openai",
    "openrouter",
    "kimi",
    "grok",
    "openai-compatible",
)
_HOSTED_PROVIDER_DEFAULTS = {
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "gemini-3.6-flash",
    ),
    "openai": ("https://api.openai.com/v1", "gpt-5-mini"),
    "openrouter": ("https://openrouter.ai/api/v1", "openai/gpt-5-mini"),
    "kimi": ("https://api.moonshot.ai/v1", "kimi-k2.5"),
    "grok": ("https://api.x.ai/v1", "grok-4.5"),
    "openai-compatible": ("http://127.0.0.1:1234/v1", "local-model"),
}


class SettingsWindow(QWidget):
    """Settings surface for companion, behavior, and voice configuration."""

    settings_saved = Signal(object)
    position_reset_requested = Signal()
    memory_manager_requested = Signal()
    behavior_history_requested = Signal()
    voice_health_check_requested = Signal()
    voice_microphone_test_requested = Signal()
    voice_output_test_requested = Signal()

    def __init__(
        self,
        config: AppConfig,
        log_dir: Path,
        data_dir: Path | None = None,
        credential_store: CredentialStore | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._log_dir = log_dir
        self._data_dir = data_dir or log_dir.parent
        self._credential_store = credential_store
        self._ai_discovery_thread: AIProviderDiscoveryThread | None = None

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
        self._ai_provider_input.addItems(
            [provider for provider in _AI_PROVIDER_ORDER if provider in AI_PROVIDERS]
        )
        self._ai_provider_input.setCurrentText(config.ai.provider)
        self._ollama_base_url_input = QLineEdit(config.ai.ollama_base_url)
        self._ollama_model_input = _ModelComboBox(config.ai.ollama_model)
        self._hosted_base_url_input = QLineEdit(config.ai.hosted_base_url)
        self._hosted_model_input = _ModelComboBox(config.ai.hosted_model)
        self._ai_api_key_input = QLineEdit()
        self._ai_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._ai_api_key_input.setPlaceholderText("Leave blank to keep saved key")
        self._ai_api_key_status = QLabel()
        self._clear_ai_api_key_button = QPushButton("Clear key")
        self._clear_ai_api_key_button.clicked.connect(self._clear_ai_api_key)
        self._ai_connection_button = QPushButton("Connect and find models")
        self._ai_connection_button.clicked.connect(self._check_ai_provider)
        self._ai_connection_status = QLabel("Not checked")
        self._ai_connection_status.setWordWrap(True)
        self._advanced_ai_settings_input = QCheckBox()
        self._advanced_ai_settings_input.toggled.connect(
            lambda _checked: self._sync_ai_controls(
                self._ai_provider_input.currentText()
            )
        )
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
        self._idle_after_input = _build_minutes_spinbox(
            1,
            1440,
            config.behavior.idle_after_seconds,
        )
        self._away_after_input = _build_minutes_spinbox(
            2,
            1440,
            config.behavior.away_after_seconds,
        )
        self._idle_after_input.valueChanged.connect(self._sync_away_minimum)
        self._sync_away_minimum(_seconds_to_minutes(config.behavior.idle_after_seconds))
        self._notification_cooldown_input = _build_minutes_spinbox(
            1,
            1440,
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
        self._scheduled_check_in_interval_input = _build_minutes_spinbox(
            1,
            1440,
            config.behavior.scheduled_check_in_interval_seconds,
        )
        self._quiet_hours_enabled_input = QCheckBox()
        self._quiet_hours_enabled_input.setChecked(config.behavior.quiet_hours_enabled)
        self._quiet_hours_start_input = _build_time_input(
            config.behavior.quiet_hours_start
        )
        self._quiet_hours_end_input = _build_time_input(config.behavior.quiet_hours_end)
        self._voice_enabled_input = QCheckBox()
        self._voice_enabled_input.setChecked(config.voice.enabled)
        self._push_to_talk_enabled_input = QCheckBox()
        self._push_to_talk_enabled_input.setChecked(config.voice.push_to_talk_enabled)
        self._voice_input_provider_input = _build_combo(
            ("faster-whisper", "disabled"),
            config.voice.input_provider,
        )
        self._voice_input_model_input = QLineEdit(config.voice.input_model)
        self._voice_input_language_input = _build_combo(
            ("auto", "ja", "en"),
            config.voice.input_language,
            editable=True,
        )
        self._voice_input_device_input = _build_device_combo(config.voice.input_device)
        self._voice_output_provider_input = _build_combo(
            ("voicevox", "disabled"),
            config.voice.output_provider,
        )
        self._voice_output_base_url_input = QLineEdit(config.voice.output_base_url)
        self._voice_output_voice_id_input = QLineEdit(config.voice.output_voice_id)
        self._voice_output_device_input = _build_device_combo(
            config.voice.output_device
        )
        self._automatic_speech_enabled_input = QCheckBox()
        self._automatic_speech_enabled_input.setChecked(
            config.voice.automatic_speech_enabled
        )
        self._proactive_speech_enabled_input = QCheckBox()
        self._proactive_speech_enabled_input.setChecked(
            config.voice.proactive_speech_enabled
        )
        self._english_subtitles_enabled_input = QCheckBox()
        self._english_subtitles_enabled_input.setChecked(
            config.voice.english_subtitles_enabled
        )
        self._english_subtitles_enabled_input.setToolTip(
            "Uses the selected AI provider for an additional translation request."
        )
        self._live_transcription_enabled_input = QCheckBox()
        self._live_transcription_enabled_input.setChecked(
            config.voice.live_transcription_enabled
        )
        self._auto_stop_on_silence_enabled_input = QCheckBox()
        self._auto_stop_on_silence_enabled_input.setChecked(
            config.voice.auto_stop_on_silence_enabled
        )
        self._auto_send_transcript_enabled_input = QCheckBox()
        self._auto_send_transcript_enabled_input.setChecked(
            config.voice.auto_send_transcript_enabled
        )
        self._voice_silence_timeout_input = QDoubleSpinBox()
        self._voice_silence_timeout_input.setRange(0.5, 5.0)
        self._voice_silence_timeout_input.setSingleStep(0.1)
        self._voice_silence_timeout_input.setDecimals(1)
        self._voice_silence_timeout_input.setValue(config.voice.silence_timeout_seconds)
        self._voice_silence_timeout_input.setSuffix(" sec")
        self._voice_volume_input = _build_spinbox(
            0,
            100,
            config.voice.volume_percent,
        )
        self._voice_volume_input.setSuffix("%")
        self._voice_speaking_rate_input = QDoubleSpinBox()
        self._voice_speaking_rate_input.setRange(0.5, 2.0)
        self._voice_speaking_rate_input.setSingleStep(0.1)
        self._voice_speaking_rate_input.setDecimals(1)
        self._voice_speaking_rate_input.setValue(config.voice.speaking_rate)
        self._voice_capture_timeout_input = _build_spinbox(
            1,
            300,
            config.voice.capture_timeout_seconds,
        )
        self._voice_capture_timeout_input.setSuffix(" sec")
        self._voice_request_timeout_input = _build_spinbox(
            1,
            300,
            config.voice.request_timeout_seconds,
        )
        self._voice_request_timeout_input.setSuffix(" sec")
        self._voice_health_check_button = QPushButton("Check setup")
        self._voice_health_check_button.clicked.connect(
            self.voice_health_check_requested.emit
        )
        self._voice_microphone_test_button = QPushButton("Test microphone")
        self._voice_microphone_test_button.clicked.connect(
            self.voice_microphone_test_requested.emit
        )
        self._voice_output_test_button = QPushButton("Test voice")
        self._voice_output_test_button.clicked.connect(
            self.voice_output_test_requested.emit
        )
        self._voice_input_health = QLabel("Not checked")
        self._voice_input_health.setWordWrap(True)
        self._voice_output_health = QLabel("Not checked")
        self._voice_output_health.setWordWrap(True)
        self._voice_diagnostic_status = QLabel("Ready")
        self._voice_diagnostic_status.setWordWrap(True)
        self._ai_provider_input.currentTextChanged.connect(
            self._handle_ai_provider_changed
        )
        self._voice_enabled_input.toggled.connect(self._sync_voice_controls)

        tabs = QTabWidget()
        tabs.addTab(self._build_pet_tab(), "Pet")
        tabs.addTab(self._build_ai_tab(), "AI")
        tabs.addTab(self._build_memory_tab(), "Memory")
        tabs.addTab(self._build_behavior_tab(), "Behavior")
        tabs.addTab(self._build_voice_tab(), "Voice")
        self._sync_ai_controls(config.ai.provider)
        self._sync_voice_controls(config.voice.enabled)

        save_button = QPushButton("Save")
        save_button.clicked.connect(self._save)

        reset_position_button = QPushButton("Reset position")
        reset_position_button.clicked.connect(self.position_reset_requested.emit)

        open_logs_button = QPushButton("Open logs")
        open_logs_button.clicked.connect(self._open_logs)

        open_data_button = QPushButton("Open data")
        open_data_button.clicked.connect(self._open_data_dir)

        memories_button = QPushButton("Memories")
        memories_button.clicked.connect(self.memory_manager_requested.emit)

        behavior_history_button = QPushButton("Behavior history")
        behavior_history_button.clicked.connect(self.behavior_history_requested.emit)

        button_layout = QHBoxLayout()
        button_layout.addWidget(save_button)
        button_layout.addWidget(reset_position_button)
        button_layout.addWidget(open_logs_button)
        button_layout.addWidget(open_data_button)
        button_layout.addWidget(memories_button)
        button_layout.addWidget(behavior_history_button)

        layout = QVBoxLayout()
        layout.addWidget(tabs)
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
        self._hosted_base_url_input.setText(config.ai.hosted_base_url)
        self._hosted_model_input.setText(config.ai.hosted_model)
        self._ai_timeout_input.setValue(config.ai.request_timeout_seconds)
        self._ai_api_key_input.clear()
        self._sync_ai_controls(config.ai.provider)
        self._character_name_input.setText(config.personality.character_name)
        self._system_prompt_input.setPlainText(config.personality.system_prompt)
        self._memory_enabled_input.setChecked(config.memory.enabled)
        self._memory_approval_input.setChecked(config.memory.require_approval)
        self._memory_retrieval_limit_input.setValue(config.memory.retrieval_limit)
        self._behavior_enabled_input.setChecked(config.behavior.enabled)
        self._proactive_enabled_input.setChecked(config.behavior.proactive_enabled)
        self._idle_after_input.setValue(
            _seconds_to_minutes(config.behavior.idle_after_seconds)
        )
        self._sync_away_minimum(_seconds_to_minutes(config.behavior.idle_after_seconds))
        self._away_after_input.setValue(
            _seconds_to_minutes(config.behavior.away_after_seconds)
        )
        self._notification_cooldown_input.setValue(
            _seconds_to_minutes(config.behavior.minimum_seconds_between_notifications)
        )
        self._allow_notifications_while_away_input.setChecked(
            config.behavior.allow_notifications_while_away
        )
        self._scheduled_check_ins_enabled_input.setChecked(
            config.behavior.scheduled_check_ins_enabled
        )
        self._scheduled_check_in_interval_input.setValue(
            _seconds_to_minutes(config.behavior.scheduled_check_in_interval_seconds)
        )
        self._quiet_hours_enabled_input.setChecked(config.behavior.quiet_hours_enabled)
        self._quiet_hours_start_input.setTime(
            _parse_qtime(config.behavior.quiet_hours_start)
        )
        self._quiet_hours_end_input.setTime(
            _parse_qtime(config.behavior.quiet_hours_end)
        )
        self._voice_enabled_input.setChecked(config.voice.enabled)
        self._push_to_talk_enabled_input.setChecked(config.voice.push_to_talk_enabled)
        self._voice_input_provider_input.setCurrentText(config.voice.input_provider)
        self._voice_input_model_input.setText(config.voice.input_model)
        self._voice_input_language_input.setCurrentText(config.voice.input_language)
        _set_device_combo_value(
            self._voice_input_device_input,
            config.voice.input_device,
        )
        self._voice_output_provider_input.setCurrentText(config.voice.output_provider)
        self._voice_output_base_url_input.setText(config.voice.output_base_url)
        self._voice_output_voice_id_input.setText(config.voice.output_voice_id)
        _set_device_combo_value(
            self._voice_output_device_input,
            config.voice.output_device,
        )
        self._automatic_speech_enabled_input.setChecked(
            config.voice.automatic_speech_enabled
        )
        self._proactive_speech_enabled_input.setChecked(
            config.voice.proactive_speech_enabled
        )
        self._english_subtitles_enabled_input.setChecked(
            config.voice.english_subtitles_enabled
        )
        self._live_transcription_enabled_input.setChecked(
            config.voice.live_transcription_enabled
        )
        self._auto_stop_on_silence_enabled_input.setChecked(
            config.voice.auto_stop_on_silence_enabled
        )
        self._auto_send_transcript_enabled_input.setChecked(
            config.voice.auto_send_transcript_enabled
        )
        self._voice_silence_timeout_input.setValue(config.voice.silence_timeout_seconds)
        self._voice_volume_input.setValue(config.voice.volume_percent)
        self._voice_speaking_rate_input.setValue(config.voice.speaking_rate)
        self._voice_capture_timeout_input.setValue(config.voice.capture_timeout_seconds)
        self._voice_request_timeout_input.setValue(config.voice.request_timeout_seconds)
        self._sync_voice_controls(config.voice.enabled)

    def set_voice_health(
        self,
        input_status: str,
        input_detail: str,
        output_status: str,
        output_detail: str,
    ) -> None:
        """Display speech provider health without exposing private content."""
        self._voice_input_health.setText(
            _format_voice_health(input_status, input_detail)
        )
        self._voice_output_health.setText(
            _format_voice_health(output_status, output_detail)
        )

    def set_voice_diagnostic_status(
        self,
        status: str,
        is_error: bool = False,
    ) -> None:
        """Display a diagnostic action result."""
        self._voice_diagnostic_status.setText(status.strip() or "Ready")
        color = "#c62828" if is_error else "#2e7d32"
        self._voice_diagnostic_status.setStyleSheet(f"color: {color};")

    def set_voice_test_active(self, test_name: str, active: bool) -> None:
        """Update the active voice test command."""
        if test_name == "microphone":
            self._voice_microphone_test_button.setText(
                "Stop microphone test" if active else "Test microphone"
            )
        elif test_name == "output":
            self._voice_output_test_button.setText(
                "Stop voice test" if active else "Test voice"
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

    def _build_pet_tab(self) -> QWidget:
        form_layout = QFormLayout()
        form_layout.addRow("Width", self._width_input)
        form_layout.addRow("Height", self._height_input)
        form_layout.addRow("FPS", self._fps_input)
        form_layout.addRow("Walking speed", self._walking_speed_input)
        form_layout.addRow("Start X", self._start_x_input)
        form_layout.addRow("Start Y", self._start_y_input)
        form_layout.addRow("Always on top", self._always_on_top_input)
        form_layout.addRow("Animation manifest", self._build_manifest_row())
        return _build_scroll_tab(form_layout)

    def _build_ai_tab(self) -> QWidget:
        form_layout = QFormLayout()
        form_layout.addRow("AI provider", self._ai_provider_input)
        form_layout.addRow(
            "Advanced provider settings",
            self._advanced_ai_settings_input,
        )
        self._ollama_url_label = QLabel("Ollama URL")
        self._ollama_model_label = QLabel("Ollama model")
        self._hosted_url_label = QLabel("Hosted API URL")
        self._hosted_model_label = QLabel("Hosted model")
        form_layout.addRow(self._ollama_url_label, self._ollama_base_url_input)
        form_layout.addRow(self._ollama_model_label, self._ollama_model_input)
        form_layout.addRow(self._hosted_url_label, self._hosted_base_url_input)
        form_layout.addRow(self._hosted_model_label, self._hosted_model_input)
        form_layout.addRow("API key", self._ai_api_key_input)
        form_layout.addRow("Credential", self._build_ai_credential_row())
        form_layout.addRow("Provider connection", self._build_ai_connection_row())
        form_layout.addRow("AI timeout", self._ai_timeout_input)
        form_layout.addRow("Companion name", self._character_name_input)
        form_layout.addRow("System prompt", self._system_prompt_input)
        return _build_scroll_tab(form_layout)

    def _build_ai_credential_row(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._ai_api_key_status, stretch=1)
        layout.addWidget(self._clear_ai_api_key_button)
        row.setLayout(layout)
        return row

    def _build_ai_connection_row(self) -> QWidget:
        row = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._ai_connection_button)
        layout.addWidget(self._ai_connection_status)
        row.setLayout(layout)
        return row

    def _build_memory_tab(self) -> QWidget:
        form_layout = QFormLayout()
        form_layout.addRow("Memory enabled", self._memory_enabled_input)
        form_layout.addRow("Approve memories", self._memory_approval_input)
        form_layout.addRow("Memory retrieval limit", self._memory_retrieval_limit_input)
        return _build_scroll_tab(form_layout)

    def _build_behavior_tab(self) -> QWidget:
        form_layout = QFormLayout()
        form_layout.addRow("Behavior enabled", self._behavior_enabled_input)
        form_layout.addRow("Proactive nudges", self._proactive_enabled_input)
        form_layout.addRow("Idle after", self._idle_after_input)
        form_layout.addRow("Away after", self._away_after_input)
        form_layout.addRow("Nudge cooldown", self._notification_cooldown_input)
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
        return _build_scroll_tab(form_layout)

    def _build_voice_tab(self) -> QWidget:
        form_layout = QFormLayout()
        form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form_layout.addRow("Voice enabled", self._voice_enabled_input)
        form_layout.addRow(
            "Push-to-talk enabled",
            self._push_to_talk_enabled_input,
        )
        form_layout.addRow(
            "Input provider",
            self._voice_input_provider_input,
        )
        form_layout.addRow("Whisper model", self._voice_input_model_input)
        form_layout.addRow(
            "Recognition language",
            self._voice_input_language_input,
        )
        form_layout.addRow(
            "Microphone",
            self._voice_input_device_input,
        )
        form_layout.addRow(
            "Output provider",
            self._voice_output_provider_input,
        )
        form_layout.addRow(
            "VOICEVOX URL",
            self._voice_output_base_url_input,
        )
        form_layout.addRow(
            "VOICEVOX speaker ID",
            self._voice_output_voice_id_input,
        )
        form_layout.addRow(
            "Speakers",
            self._voice_output_device_input,
        )
        form_layout.addRow(
            "Speak replies automatically",
            self._automatic_speech_enabled_input,
        )
        form_layout.addRow(
            "Speak proactive check-ins",
            self._proactive_speech_enabled_input,
        )
        form_layout.addRow(
            "Show English subtitles",
            self._english_subtitles_enabled_input,
        )
        form_layout.addRow(
            "Show transcription while speaking",
            self._live_transcription_enabled_input,
        )
        form_layout.addRow(
            "Stop recording after silence",
            self._auto_stop_on_silence_enabled_input,
        )
        form_layout.addRow(
            "Send final transcript automatically",
            self._auto_send_transcript_enabled_input,
        )
        form_layout.addRow(
            "Silence duration",
            self._voice_silence_timeout_input,
        )
        form_layout.addRow("Volume", self._voice_volume_input)
        form_layout.addRow("Speaking rate", self._voice_speaking_rate_input)
        form_layout.addRow(
            "Recording timeout",
            self._voice_capture_timeout_input,
        )
        form_layout.addRow(
            "Provider timeout",
            self._voice_request_timeout_input,
        )
        form_layout.addRow("Provider check", self._voice_health_check_button)
        form_layout.addRow("Microphone test", self._voice_microphone_test_button)
        form_layout.addRow("Voice test", self._voice_output_test_button)
        form_layout.addRow("Speech recognition", self._voice_input_health)
        form_layout.addRow("Speech output", self._voice_output_health)
        form_layout.addRow("Diagnostic status", self._voice_diagnostic_status)
        return _build_scroll_tab(form_layout)

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
        if not self._validate_ai_inputs():
            return
        if not self._save_ai_api_key():
            return
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
                hosted_base_url=self._hosted_base_url_input.text(),
                hosted_model=self._hosted_model_input.text(),
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
                idle_after_seconds=_minutes_to_seconds(self._idle_after_input.value()),
                away_after_seconds=_minutes_to_seconds(self._away_after_input.value()),
                minimum_seconds_between_notifications=(
                    _minutes_to_seconds(self._notification_cooldown_input.value())
                ),
                allow_notifications_while_away=(
                    self._allow_notifications_while_away_input.isChecked()
                ),
                scheduled_check_ins_enabled=(
                    self._scheduled_check_ins_enabled_input.isChecked()
                ),
                scheduled_check_in_interval_seconds=(
                    _minutes_to_seconds(self._scheduled_check_in_interval_input.value())
                ),
                quiet_hours_enabled=self._quiet_hours_enabled_input.isChecked(),
                quiet_hours_start=_format_time_input(self._quiet_hours_start_input),
                quiet_hours_end=_format_time_input(self._quiet_hours_end_input),
            )
        )
        config = config.with_voice(
            VoiceConfig(
                enabled=self._voice_enabled_input.isChecked(),
                push_to_talk_enabled=(self._push_to_talk_enabled_input.isChecked()),
                input_provider=self._voice_input_provider_input.currentText(),
                input_model=self._voice_input_model_input.text(),
                input_language=self._voice_input_language_input.currentText(),
                input_device=_selected_device_name(self._voice_input_device_input),
                output_provider=self._voice_output_provider_input.currentText(),
                output_base_url=self._voice_output_base_url_input.text(),
                output_voice_id=self._voice_output_voice_id_input.text(),
                output_device=_selected_device_name(self._voice_output_device_input),
                automatic_speech_enabled=(
                    self._automatic_speech_enabled_input.isChecked()
                ),
                proactive_speech_enabled=(
                    self._proactive_speech_enabled_input.isChecked()
                ),
                english_subtitles_enabled=(
                    self._english_subtitles_enabled_input.isChecked()
                ),
                live_transcription_enabled=(
                    self._live_transcription_enabled_input.isChecked()
                ),
                auto_stop_on_silence_enabled=(
                    self._auto_stop_on_silence_enabled_input.isChecked()
                ),
                auto_send_transcript_enabled=(
                    self._auto_send_transcript_enabled_input.isChecked()
                ),
                silence_timeout_seconds=self._voice_silence_timeout_input.value(),
                volume_percent=self._voice_volume_input.value(),
                speaking_rate=self._voice_speaking_rate_input.value(),
                capture_timeout_seconds=(self._voice_capture_timeout_input.value()),
                request_timeout_seconds=(self._voice_request_timeout_input.value()),
            )
        )
        self.update_config(config)
        self.settings_saved.emit(config)

    def _sync_away_minimum(self, idle_after_minutes: int) -> None:
        self._away_after_input.setMinimum(idle_after_minutes + 1)

    def _handle_ai_provider_changed(self, provider: str) -> None:
        defaults = _HOSTED_PROVIDER_DEFAULTS.get(provider)
        if defaults is not None:
            self._hosted_base_url_input.setText(defaults[0])
            self._hosted_model_input.setText(defaults[1])
        self._set_ai_connection_status("Not checked")
        self._sync_ai_controls(provider)

    def _sync_ai_controls(self, provider: str) -> None:
        uses_ollama = provider == "ollama"
        uses_hosted_api = provider in HOSTED_AI_PROVIDERS
        uses_connection = uses_ollama or uses_hosted_api
        advanced = self._advanced_ai_settings_input.isChecked()
        custom_provider = provider == "openai-compatible"
        self._ollama_base_url_input.setEnabled(uses_ollama)
        self._ollama_model_input.setEnabled(uses_ollama)
        self._hosted_base_url_input.setEnabled(uses_hosted_api)
        self._hosted_model_input.setEnabled(uses_hosted_api)
        self._ai_api_key_input.setEnabled(uses_hosted_api)
        self._clear_ai_api_key_button.setEnabled(uses_hosted_api)
        self._advanced_ai_settings_input.setVisible(uses_connection)
        self._set_row_visible(
            self._ollama_url_label,
            self._ollama_base_url_input,
            uses_ollama and advanced,
        )
        self._set_row_visible(
            self._ollama_model_label,
            self._ollama_model_input,
            uses_ollama,
        )
        self._set_row_visible(
            self._hosted_url_label,
            self._hosted_base_url_input,
            uses_hosted_api and (advanced or custom_provider),
        )
        self._set_row_visible(
            self._hosted_model_label,
            self._hosted_model_input,
            uses_hosted_api,
        )
        self._ai_connection_button.setEnabled(
            uses_connection and self._ai_discovery_thread is None
        )
        self._refresh_ai_api_key_status(provider)

    @staticmethod
    def _set_row_visible(label: QLabel, field: QWidget, visible: bool) -> None:
        label.setVisible(visible)
        field.setVisible(visible)

    def _validate_ai_inputs(self) -> bool:
        provider = self._ai_provider_input.currentText()
        model = ""
        if provider == "ollama":
            model = self._ollama_model_input.text()
        elif provider in HOSTED_AI_PROVIDERS:
            model = self._hosted_model_input.text()
        if _looks_like_api_key(model):
            self._set_ai_connection_status(
                "The model field appears to contain an API key. "
                "Move it to the protected API key field.",
                is_error=True,
            )
            return False
        return True

    def _check_ai_provider(self) -> None:
        if self._ai_discovery_thread is not None:
            return
        provider = self._ai_provider_input.currentText()
        if provider not in {"ollama", *HOSTED_AI_PROVIDERS}:
            self._set_ai_connection_status("No connection is required.")
            return
        if not self._validate_ai_inputs():
            return
        api_key = self._ai_api_key_input.text().strip()
        if not api_key and provider in HOSTED_AI_PROVIDERS:
            api_key = self._read_saved_ai_api_key(provider)
        if provider in HOSTED_AI_PROVIDERS - {"openai-compatible"} and not api_key:
            self._set_ai_connection_status(
                "Enter or save an API key before checking this provider.",
                is_error=True,
            )
            return

        base_url = (
            self._ollama_base_url_input.text()
            if provider == "ollama"
            else self._hosted_base_url_input.text()
        )
        request = AIProviderDiscoveryRequest(
            provider=provider,
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=float(self._ai_timeout_input.value()),
        )
        thread = AIProviderDiscoveryThread(request, parent=self)
        self._ai_discovery_thread = thread
        self._ai_connection_button.setEnabled(False)
        self._set_ai_connection_status("Connecting...")
        thread.models_ready.connect(self._handle_ai_models_ready)
        thread.discovery_failed.connect(self._handle_ai_discovery_failed)
        thread.finished.connect(self._finish_ai_discovery)
        thread.start()

    def _read_saved_ai_api_key(self, provider: str) -> str:
        if self._credential_store is None:
            return ""
        try:
            return self._credential_store.get_secret(provider) or ""
        except CredentialStoreError:
            self._set_ai_connection_status(
                "The saved API key could not be read.",
                is_error=True,
            )
            return ""

    def _handle_ai_models_ready(self, result: object) -> None:
        if not isinstance(result, AIProviderDiscoveryResult):
            self._set_ai_connection_status(
                "The provider returned an invalid discovery result.",
                is_error=True,
            )
            return
        if result.provider != self._ai_provider_input.currentText():
            self._set_ai_connection_status(
                "Provider changed before the connection check completed."
            )
            return
        model_input = (
            self._ollama_model_input
            if result.provider == "ollama"
            else self._hosted_model_input
        )
        preferred = model_input.text()
        preset = _HOSTED_PROVIDER_DEFAULTS.get(result.provider)
        if preset is not None and preset[1] in result.models:
            preferred = preset[1]
        model_input.set_options(result.models, preferred=preferred)
        noun = "model" if len(result.models) == 1 else "models"
        self._set_ai_connection_status(f"Connected. Found {len(result.models)} {noun}.")

    def _handle_ai_discovery_failed(self, message: str) -> None:
        self._set_ai_connection_status(
            message.strip() or "Provider connection failed.",
            is_error=True,
        )

    def _finish_ai_discovery(self) -> None:
        thread = self._ai_discovery_thread
        self._ai_discovery_thread = None
        self._sync_ai_controls(self._ai_provider_input.currentText())
        if thread is not None:
            thread.deleteLater()

    def _set_ai_connection_status(
        self,
        status: str,
        *,
        is_error: bool = False,
    ) -> None:
        self._ai_connection_status.setText(status.strip() or "Not checked")
        color = "#c62828" if is_error else "#2e7d32"
        self._ai_connection_status.setStyleSheet(f"color: {color};")

    def cancel_ai_discovery(self, wait_ms: int = 16_000) -> bool:
        """Wait for an in-flight provider check before application shutdown."""
        thread = self._ai_discovery_thread
        if thread is None:
            return True
        return thread.wait(wait_ms)

    def _refresh_ai_api_key_status(self, provider: str) -> None:
        if provider not in HOSTED_AI_PROVIDERS:
            self._ai_api_key_status.setText("Not required")
            return
        if self._credential_store is None:
            self._ai_api_key_status.setText("Secure storage unavailable")
            return
        try:
            has_key = self._credential_store.get_secret(provider) is not None
        except CredentialStoreError:
            self._ai_api_key_status.setText("Saved key could not be read")
            return
        self._ai_api_key_status.setText(
            "API key saved securely" if has_key else "No API key saved"
        )

    def _save_ai_api_key(self) -> bool:
        provider = self._ai_provider_input.currentText()
        api_key = self._ai_api_key_input.text().strip()
        if provider not in HOSTED_AI_PROVIDERS or not api_key:
            return True
        if self._credential_store is None:
            self._ai_api_key_status.setText("Secure storage unavailable")
            return False
        try:
            self._credential_store.set_secret(provider, api_key)
        except CredentialStoreError:
            self._ai_api_key_status.setText("API key could not be saved")
            return False
        self._ai_api_key_input.clear()
        self._refresh_ai_api_key_status(provider)
        return True

    def _clear_ai_api_key(self) -> None:
        provider = self._ai_provider_input.currentText()
        if self._credential_store is None:
            self._ai_api_key_status.setText("Secure storage unavailable")
            return
        try:
            self._credential_store.delete_secret(provider)
        except CredentialStoreError:
            self._ai_api_key_status.setText("API key could not be deleted")
            return
        self._ai_api_key_input.clear()
        self._refresh_ai_api_key_status(provider)

    def _sync_voice_controls(self, enabled: bool) -> None:
        for control in (
            self._push_to_talk_enabled_input,
            self._voice_input_provider_input,
            self._voice_input_model_input,
            self._voice_input_language_input,
            self._voice_input_device_input,
            self._voice_output_provider_input,
            self._voice_output_base_url_input,
            self._voice_output_voice_id_input,
            self._voice_output_device_input,
            self._automatic_speech_enabled_input,
            self._proactive_speech_enabled_input,
            self._english_subtitles_enabled_input,
            self._live_transcription_enabled_input,
            self._auto_stop_on_silence_enabled_input,
            self._auto_send_transcript_enabled_input,
            self._voice_silence_timeout_input,
            self._voice_volume_input,
            self._voice_speaking_rate_input,
            self._voice_capture_timeout_input,
            self._voice_request_timeout_input,
            self._voice_health_check_button,
            self._voice_microphone_test_button,
            self._voice_output_test_button,
        ):
            control.setEnabled(enabled)

    def _open_logs(self) -> None:
        _open_directory(self._log_dir)

    def _open_data_dir(self) -> None:
        _open_directory(self._data_dir)


def _build_spinbox(minimum: int, maximum: int, value: int) -> QSpinBox:
    spinbox = QSpinBox()
    spinbox.setRange(minimum, maximum)
    spinbox.setValue(value)
    return spinbox


class _ModelComboBox(QComboBox):
    """Editable model selector that preserves the previous line-edit API."""

    def __init__(self, value: str) -> None:
        super().__init__()
        self.setEditable(True)
        self.setText(value)

    def text(self) -> str:
        return self.currentText().strip()

    def setText(self, value: str) -> None:
        self.setCurrentText(value)

    def set_options(self, options: tuple[str, ...], *, preferred: str) -> None:
        selected = preferred if preferred in options else options[0]
        self.blockSignals(True)
        self.clear()
        self.addItems(options)
        self.setCurrentText(selected)
        self.blockSignals(False)


def _looks_like_api_key(value: str) -> bool:
    candidate = value.strip()
    if not candidate:
        return False
    prefixes = ("AIza", "xai-", "sk-", "Bearer ")
    return candidate.startswith(prefixes) and len(candidate) >= 20


def _format_voice_health(status: str, detail: str) -> str:
    label = status.strip().replace("_", " ").capitalize() or "Unknown"
    cleaned_detail = detail.strip()
    return f"{label}: {cleaned_detail}" if cleaned_detail else label


def _build_combo(
    options: tuple[str, ...],
    value: str,
    *,
    editable: bool = False,
) -> QComboBox:
    combo = QComboBox()
    combo.setEditable(editable)
    combo.addItems(options)
    combo.setCurrentText(value)
    return combo


def _build_device_combo(device_name: str) -> QComboBox:
    combo = QComboBox()
    combo.setEditable(True)
    combo.addItem("System default", "")
    _set_device_combo_value(combo, device_name)
    return combo


def _set_device_combo_value(combo: QComboBox, device_name: str) -> None:
    if not device_name:
        combo.setCurrentIndex(0)
        return
    index = combo.findData(device_name)
    if index < 0:
        combo.addItem(device_name, device_name)
        index = combo.count() - 1
    combo.setCurrentIndex(index)


def _selected_device_name(combo: QComboBox) -> str:
    current_text = combo.currentText().strip()
    if current_text != "System default":
        return current_text
    data = combo.currentData()
    if isinstance(data, str):
        return data
    return current_text


def _build_minutes_spinbox(minimum: int, maximum: int, value_seconds: int) -> QSpinBox:
    spinbox = _build_spinbox(minimum, maximum, _seconds_to_minutes(value_seconds))
    spinbox.setSuffix(" min")
    return spinbox


def _build_scroll_tab(form_layout: QFormLayout) -> QScrollArea:
    form_container = QWidget()
    form_container.setLayout(form_layout)

    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setWidget(form_container)
    return scroll_area


def _seconds_to_minutes(seconds: int) -> int:
    return max(1, ceil(seconds / 60))


def _minutes_to_seconds(minutes: int) -> int:
    return minutes * 60


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


def _open_directory(path: Path) -> bool:
    path.mkdir(parents=True, exist_ok=True)
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
