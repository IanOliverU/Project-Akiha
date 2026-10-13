"""Trusted-local utility controls; transient information never enters chat."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from PySide6.QtCore import QDateTime, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from project_akiha.config import UtilitiesConfig
from project_akiha.core.actions import ActionRequest
from project_akiha.core.utilities.timers import MAX_TIMER_SECONDS, validate_timer_input


class UtilitiesPanel(QWidget):
    action_requested = Signal(object)
    export_requested = Signal()

    def __init__(self, config: UtilitiesConfig, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._views = QTabWidget()
        layout.addWidget(self._views)
        self._status = QLabel("Schedules not checked.")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self._schedules = QListWidget()
        self._schedules.setAccessibleName("Active local schedules")
        self._schedules.setMinimumHeight(150)
        layout.addWidget(self._schedules)
        timer = QWidget()
        timer_form = QFormLayout(timer)
        self._seconds = QSpinBox()
        self._seconds.setRange(1, MAX_TIMER_SECONDS)
        self._seconds.setValue(60)
        self._label = QLineEdit()
        self._label.setMaxLength(64)
        timer_form.addRow("Duration (seconds)", self._seconds)
        timer_form.addRow("Private timer label", self._label)
        create = QPushButton("Create timer now")
        create.clicked.connect(self._create_timer)
        timer_form.addRow(create)
        self._views.addTab(timer, "Timer")
        reminder = QWidget()
        reminder_form = QFormLayout(reminder)
        self._reminder_label = QLineEdit()
        self._reminder_label.setMaxLength(64)
        self._date = QDateTimeEdit()
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("dd MMM yyyy  HH:mm")
        self._date.setDateTime(QDateTime.currentDateTimeUtc().addSecs(3600))
        self._zone = QComboBox()
        self._zone.setObjectName("settingsComboBox")
        self._zone.setEditable(True)
        self._zone.addItems(sorted(available_timezones()))
        self._zone.setCurrentText("UTC")
        self._zone.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._zone.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self._zone.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._reminder_time_edited = False
        self._date.dateTimeChanged.connect(
            lambda _: setattr(self, "_reminder_time_edited", True)
        )
        self._zone.activated.connect(self._reminder_zone_changed)
        reminder_form.addRow("Date and time", self._date)
        reminder_form.addRow("Explicit timezone", self._zone)
        reminder_form.addRow("Private reminder label", self._reminder_label)
        create_reminder = QPushButton("Create one-shot reminder now")
        create_reminder.clicked.connect(self._create_reminder)
        reminder_form.addRow(create_reminder)
        self._views.addTab(reminder, "Reminder")
        weather = QWidget()
        weather_layout = QVBoxLayout(weather)
        notice = QLabel(
            "Weather sends your explicitly approved coordinates to Open-M"
            "eteo. Optional US official alerts use NWS. Save configuratio"
            "n before requesting; results stay transient and local."
        )
        notice.setWordWrap(True)
        weather_layout.addWidget(notice)
        self._weather_enabled = QCheckBox("Enable read-only weather requests")
        self._location_configured = QCheckBox(
            "Approve sending the coordinates entered below"
        )
        self._alerts = QCheckBox("Official US NWS alerts (coverage limited)")
        weather_layout.addWidget(self._weather_enabled)
        weather_layout.addWidget(self._location_configured)
        coordinates = QFormLayout()
        self._latitude = QDoubleSpinBox()
        self._latitude.setRange(-90, 90)
        self._latitude.setDecimals(5)
        self._longitude = QDoubleSpinBox()
        self._longitude.setRange(-180, 180)
        self._longitude.setDecimals(5)
        coordinates.addRow("Latitude", self._latitude)
        coordinates.addRow("Longitude", self._longitude)
        weather_layout.addLayout(coordinates)
        weather_layout.addWidget(self._alerts)
        requests = QHBoxLayout()
        for title, action in [
            ("Current weather", "information.weather.current"),
            ("3-day forecast", "information.weather.forecast"),
        ]:
            button = QPushButton(title)
            button.clicked.connect(
                lambda _checked=False, a=action: self._request(
                    a, {"service": "weather"}
                )
            )
            requests.addWidget(button)
        weather_layout.addLayout(requests)
        self._weather = QLabel()
        self._weather.setTextFormat(Qt.TextFormat.PlainText)
        self._weather.setWordWrap(True)
        weather_layout.addWidget(self._weather)
        self._views.addTab(weather, "Weather")
        data = QWidget()
        data_layout = QFormLayout(data)
        self._retention = QSpinBox()
        self._retention.setRange(1, 365)
        data_layout.addRow("Completed label retention (days)", self._retention)
        explanation = QLabel(
            "Retention is configuration: Save Changes applies it. Export "
            "is an immediate local operation with selection, destination "
            "and a separate confirmation. No import or restore."
        )
        explanation.setWordWrap(True)
        data_layout.addRow(explanation)
        export = QPushButton("Select conversations / memories to export?")
        export.clicked.connect(self.export_requested.emit)
        data_layout.addRow(export)
        self._views.addTab(data, "Data & export")
        actions = QHBoxLayout()
        cancel = QPushButton("Cancel selected schedule now")
        cancel.clicked.connect(self._cancel)
        actions.addWidget(cancel)
        self._snooze_seconds = QSpinBox()
        self._snooze_seconds.setRange(1, MAX_TIMER_SECONDS)
        self._snooze_seconds.setValue(300)
        self._snooze_seconds.setAccessibleName("Reminder snooze duration in seconds")
        actions.addWidget(self._snooze_seconds)
        snooze = QPushButton("Snooze selected reminder now")
        snooze.clicked.connect(self._snooze)
        actions.addWidget(snooze)
        layout.addLayout(actions)
        for control in (
            self._latitude,
            self._longitude,
            self._retention,
            self._seconds,
            self._snooze_seconds,
        ):
            control.setObjectName("settingsStepper")
        for toggle in (self._weather_enabled, self._location_configured, self._alerts):
            toggle.setObjectName("settingsToggle")
        self.set_config(config)
        self._views.currentChanged.connect(self._fit_creation_page)
        self._fit_creation_page()

    def _fit_creation_page(self, *_):
        self._views.setFixedHeight(self._views.currentWidget().sizeHint().height() + 52)

    def set_config(self, config):
        self._weather_enabled.setChecked(config.weather_enabled)
        self._location_configured.setChecked(config.location_configured)
        self._latitude.setValue(config.latitude)
        self._longitude.setValue(config.longitude)
        self._alerts.setChecked(config.official_alerts)
        self._retention.setValue(config.schedule_label_retention_days)
        self._weather.setText(
            "Weather not requested. Save location settings before requesting weather."
        )

    def config(self):
        return UtilitiesConfig(
            self._weather_enabled.isChecked(),
            self._location_configured.isChecked(),
            self._latitude.value(),
            self._longitude.value(),
            self._alerts.isChecked(),
            self._retention.value(),
        )

    def show_weather(self, text):
        self._weather.setText(text)
        self._views.setCurrentIndex(2)
        self._fit_creation_page()

    def _reminder_zone_changed(self, *_):
        if self._reminder_time_edited:
            return
        try:
            zone = ZoneInfo(self._zone.currentText())
        except (ValueError, ZoneInfoNotFoundError):
            return
        value = (datetime.now(zone) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        self._date.setDateTime(QDateTime.fromString(value, "yyyy-MM-ddTHH:mm"))
        self._reminder_time_edited = False

    def update_schedules(self, timers, reminders):
        selected = self._schedules.currentItem()
        selected_id = selected.data(256) if selected else None
        self._schedules.clear()
        for record in (*timers, *reminders):
            identifier = getattr(
                record, "timer_id", getattr(record, "reminder_id", None)
            )
            title = "Timer" if hasattr(record, "timer_id") else "Reminder"
            self._schedules.addItem(
                f'{title}: {record.label or "Unnamed"}; '
                f"{record.due_at.isoformat()} ({getattr(record,'timezone','UTC')}); "
                f"{record.status.value}\n{identifier}"
            )
            item = self._schedules.item(self._schedules.count() - 1)
            item.setData(256, identifier)
            if identifier == selected_id:
                self._schedules.setCurrentItem(item)
        self._status.setText(
            f"Active schedules: {len(timers)} timers, {len(reminders)} reminders. "
            "Due notifications follow your existing quiet-hours, activity "
            "and channel preferences. Missed reminders over one hour "
            "appear silently in Notification Center."
        )

    def _request(self, action_id, parameters):
        self.action_requested.emit(
            ActionRequest("local-utility-" + uuid4().hex, action_id, "chat", parameters)
        )

    def _label_valid(self, field=None):
        try:
            validate_timer_input(1, (field or self._label).text().strip())
        except ValueError:
            self._status.setText(
                "Use up to 64 letters, digits, spaces, "
                "underscores or hyphens for the local label."
            )
            return False
        return True

    def _create_timer(self):
        if self._label_valid():
            self._request(
                "timers.create",
                {
                    "service": "timers",
                    "duration_seconds": self._seconds.value(),
                    "label": self._label.text().strip(),
                },
            )

    def _create_reminder(self):
        if self._label_valid(self._reminder_label):
            try:
                ZoneInfo(self._zone.currentText())
            except (ValueError, ZoneInfoNotFoundError):
                self._status.setText("Choose a supported explicit IANA timezone.")
                return
            self._request(
                "reminders.create",
                {
                    "service": "reminders",
                    "local_time": self._date.dateTime().toString("yyyy-MM-ddTHH:mm"),
                    "timezone": self._zone.currentText(),
                    "label": self._reminder_label.text().strip(),
                },
            )

    def _selected_id(self):
        item = self._schedules.currentItem()
        return item.data(256) if item else None

    def _cancel(self):
        identifier = self._selected_id()
        if identifier:
            reminder = identifier.startswith("reminder-")
            self._request(
                "reminders.cancel" if reminder else "timers.cancel",
                {
                    "service": "reminders" if reminder else "timers",
                    "reminder_id" if reminder else "timer_id": identifier,
                },
            )

    def _snooze(self):
        identifier = self._selected_id()
        if identifier and identifier.startswith("reminder-"):
            self._request(
                "reminders.snooze",
                {
                    "service": "reminders",
                    "reminder_id": identifier,
                    "duration_seconds": self._snooze_seconds.value(),
                },
            )
        else:
            self._status.setText("Select an active reminder to snooze.")
