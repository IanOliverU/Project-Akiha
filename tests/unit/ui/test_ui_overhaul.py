"""Native presentation interactions without replacing action or data authority."""

import os
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QStyle
from shiboken6 import isValid

from project_akiha.config import AppConfig, UtilitiesConfig
from project_akiha.ui.chat_window import ChatWindow
from project_akiha.ui.fluent_icons import fluent_icon
from project_akiha.ui.menus import polish_menu
from project_akiha.ui.settings_window import SettingsWindow
from project_akiha.ui.user_export_dialog import UserExportDialog
from project_akiha.ui.utilities_panel import UtilitiesPanel


class UIOverhaulTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widgets = []
        self.temp = TemporaryDirectory()

    def tearDown(self):
        for widget in self.widgets:
            if isValid(widget):
                if isinstance(widget, SettingsWindow):
                    widget._draft_dirty = False
                widget.close()
                widget.deleteLater()
        self.widgets.clear()
        self.app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.temp.cleanup()

    def chat(self):
        window = ChatWindow()
        self.widgets.append(window)
        window.show()
        self.app.processEvents()
        return window

    def settings(self):
        window = SettingsWindow(AppConfig(), Path(self.temp.name) / "logs")
        self.widgets.append(window)
        window.show()
        self.app.processEvents()
        return window

    def test_original_palette_is_shared_by_redesigned_surfaces(self):
        from project_akiha.ui import theme

        expected = {
            "window": "#1A1D24",
            "panel": "#22252E",
            "control": "#2C303C",
            "border": "#3A3F52",
            "text": "#E8E9EE",
            "muted_text": "#9A9FB5",
            "primary": "#7B7FC4",
            "highlight": "#9599E0",
            "listening_border": "#4A5FC7",
            "listening": "#5B6FD4",
            "speaking": "#B6BADF",
            "success": "#78B892",
            "error": "#D87582",
        }
        for name, value in expected.items():
            self.assertEqual(getattr(theme.AKIHA_PALETTE, name), value)
        for factory in (
            theme.native_surface_stylesheet,
            theme.settings_stylesheet,
            theme.chat_stylesheet,
            theme.memory_window_stylesheet,
            theme.behavior_history_stylesheet,
            theme.action_history_stylesheet,
            theme.pet_care_stylesheet,
            theme.pet_status_stylesheet,
            theme.shop_window_stylesheet,
        ):
            with self.subTest(surface=factory.__name__):
                style = factory()
                self.assertIn(expected["text"], style)
                self.assertTrue(
                    any(expected[key] in style for key in ("window", "panel"))
                )
                for replaced in ("#181819", "#202021", "#2B2B2E", "#38383D"):
                    self.assertNotIn(replaced, style)

    def test_enter_sends_shift_enter_newline_and_payload_preserved(self):
        window = self.chat()
        messages = []
        window.message_submitted.connect(messages.append)
        window._input.setFocus()
        QTest.keyClicks(window._input, "first")
        QTest.keyClick(
            window._input, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier
        )
        QTest.keyClicks(window._input, "second")
        self.assertEqual(window._input.text(), "first\nsecond")
        QTest.keyClick(window._input, Qt.Key.Key_Return)
        self.assertEqual(messages, ["first\nsecond"])
        self.assertEqual(window._input.text(), "")

    def test_voice_insertion_respects_multiline_cursor(self):
        window = self.chat()
        window._input.setText("first\nlast")
        window._input.setCursorPosition(6)
        window.insert_voice_transcript("spoken")
        self.assertEqual(window._input.text(), "first\nspoken last")

    def test_multiline_stream_replacement_does_not_duplicate_or_erase_subtitle(self):
        window = self.chat()
        window.begin_streaming_message("Akiha")
        window.replace_streaming_message("Akiha", "old\nsecond")
        window.replace_streaming_message("Akiha", "new\nsecond")
        window.finish_streaming_message()
        window.append_assistant_translation("Synthetic translation")
        text = window._history_view.toPlainText()
        self.assertNotIn("old", text)
        self.assertEqual(text.count("Akiha:"), 1)
        self.assertIn("new\nsecond", text)
        self.assertIn("English: Synthetic translation", text)

    def test_reader_scroll_and_selection_survive_append_and_stream(self):
        window = self.chat()
        for i in range(90):
            window.append_message("You", f"Synthetic paragraph {i}")
        bar = window._history_view.verticalScrollBar()
        bar.setValue(0)
        cursor = window._history_view.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(3, QTextCursor.MoveMode.KeepAnchor)
        window._history_view.setTextCursor(cursor)
        window.append_message("Akiha", "additional")
        self.assertEqual(bar.value(), 0)
        self.assertEqual(window._history_view.textCursor().selectedText(), "You")
        window.begin_streaming_message("Akiha")
        window.append_stream_delta("late stream")
        self.assertEqual(bar.value(), 0)

    def test_settings_search_never_indexes_editor_or_dynamic_private_values(self):
        window = self.settings()
        window._ai_api_key_input.setText("PRIVATE_SEARCH_SENTINEL")
        window._settings_search.setText("PRIVATE_SEARCH_SENTINEL")
        self.assertTrue(
            all(button.isHidden() for button in window._settings_nav_buttons)
        )
        self.assertIn("No setting label matches", window._save_status.text())
        window._settings_search.setText("microphone")
        self.assertEqual(window._tabs.currentIndex(), 7)
        self.assertEqual(window._ai_api_key_input.text(), "PRIVATE_SEARCH_SENTINEL")

    def test_navigation_keeps_draft_and_external_update_does_not_discard_it(self):
        window = self.settings()
        window._mark_unsaved()
        window._manifest_path_input.setText("synthetic-draft.toml")
        window.open_page("Voice")
        window.update_config(
            replace(
                AppConfig(), utilities=UtilitiesConfig(schedule_label_retention_days=40)
            )
        )
        self.assertEqual(window._manifest_path_input.text(), "synthetic-draft.toml")
        self.assertTrue(window._draft_dirty)

    def test_typing_editable_model_marks_configuration_unsaved(self):
        window = self.settings()
        window.open_page("AI")
        window._ai_provider_input.setCurrentText("ollama")
        self.assertTrue(window._ollama_model_input.isEnabled())
        editor = window._ollama_model_input.lineEdit()
        editor.setFocus()
        QTest.keyClicks(editor, "synthetic-model")
        self.assertTrue(window._draft_dirty)

    def test_unsaved_close_cancel_preserves_and_discard_restores(self):
        window = self.settings()
        original = window._manifest_path_input.text()
        window._mark_unsaved()
        window._manifest_path_input.setText("changed.toml")
        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel
        ):
            self.assertFalse(window.close())
        self.assertTrue(window._draft_dirty)
        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.Discard
        ):
            self.assertTrue(window.close())
        self.assertEqual(window._manifest_path_input.text(), original)

    def test_save_error_retains_draft_and_does_not_claim_saved(self):
        window = self.settings()
        saved = window._config
        window._mark_unsaved()
        window._fps_input.setValue(45)
        window.settings_saved.connect(lambda _: window.mark_save_result(False))
        self.assertFalse(window._save())
        self.assertTrue(window._draft_dirty)
        self.assertIn("could not be saved", window._save_status.text())
        self.assertEqual(window._config, saved)
        self.assertEqual(window._fps_input.value(), 45)

    def test_weather_results_reveal_weather_page_and_keep_only_local_text(self):
        panel = UtilitiesPanel(UtilitiesConfig())
        self.widgets.append(panel)
        panel.show_weather("SYNTHETIC_LOCAL_WEATHER")
        self.assertEqual(panel._views.currentIndex(), 2)
        self.assertEqual(panel._weather.text(), "SYNTHETIC_LOCAL_WEATHER")

    def test_native_reminder_date_zone_produces_existing_typed_request(self):
        panel = UtilitiesPanel(UtilitiesConfig())
        self.widgets.append(panel)
        emitted = []
        panel.action_requested.connect(emitted.append)
        panel._date.setDateTime(panel._date.dateTime().addDays(1))
        panel._zone.setCurrentText("Asia/Taipei")
        panel._reminder_label.setText("synthetic reminder")
        panel._create_reminder()
        request = emitted[0]
        self.assertEqual(request.action_id, "reminders.create")
        self.assertEqual(request.parameters["timezone"], "Asia/Taipei")
        self.assertEqual(request.parameters["label"], "synthetic reminder")
        self.assertRegex(
            request.parameters["local_time"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$"
        )
        panel._zone.setCurrentText("Unsupported/PRIVATE")
        panel._create_reminder()
        self.assertEqual(len(emitted), 1)

    def test_export_view_uses_local_snapshot_no_service_and_explicit_selection(self):
        dialog = UserExportDialog(
            {"conversations": ((1, "Synthetic record"),), "memories": ()}
        )
        self.widgets.append(dialog)
        self.assertFalse(hasattr(dialog, "service"))
        self.assertEqual(dialog.selection(), ())
        dialog.records.item(0).setCheckState(Qt.CheckState.Checked)
        self.assertEqual(dialog.selection(), (1,))

    def test_navigation_signals_are_local_and_icons_are_bundled(self):
        window = self.chat()
        emitted = []
        window.destination_requested.connect(emitted.append)
        for key, button in window._destinations.items():
            button.click()
            self.assertEqual(emitted[-1], key)
            self.assertFalse(button.icon().isNull())
            self.assertTrue(button.accessibleName())
        self.assertFalse(fluent_icon("settings").isNull())

    def test_context_menu_overflow_remains_native_scrollable_and_keyboard_reachable(
        self,
    ):
        menu = QMenu()
        self.widgets.append(menu)
        for index in range(40):
            menu.addAction("Synthetic command " + str(index))
        polish_menu(menu)
        self.assertEqual(menu.style().styleHint(QStyle.StyleHint.SH_Menu_Scrollable), 1)
        menu.popup(self.app.primaryScreen().availableGeometry().center())
        self.app.processEvents()
        QTest.keyClick(menu, Qt.Key.Key_End)
        self.assertEqual(menu.activeAction().text(), "Synthetic command 39")
