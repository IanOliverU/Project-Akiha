"""Tests for the chat window."""

from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from project_akiha.ui.chat_window import ChatWindow


class ChatWindowTest(unittest.TestCase):
    """Verify chat transcript rendering helpers."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def test_appends_idle_check_in_as_proactive_suggestion(self) -> None:
        window = ChatWindow()

        window.append_proactive_suggestion("Need a short break?", "idle_check_in")

        self.assertIn("Akiha check-in", window._history_view.toPlainText())
        self.assertIn("Need a short break?", window._history_view.toPlainText())

    def test_appends_scheduled_check_in_label(self) -> None:
        window = ChatWindow()

        window.append_proactive_suggestion("Still doing okay?", "scheduled_check_in")

        self.assertIn("Akiha scheduled check-in", window._history_view.toPlainText())

    def test_escapes_proactive_suggestion_content(self) -> None:
        window = ChatWindow()

        window.append_proactive_suggestion("<b>Take a break</b>", "unknown")

        self.assertIn("Akiha suggestion", window._history_view.toPlainText())
        self.assertIn("<b>Take a break</b>", window._history_view.toPlainText())
        self.assertNotIn("<b>Take a break</b>", window._history_view.toHtml())

    def test_sets_presence_text_without_touching_status(self) -> None:
        window = ChatWindow()
        window.set_status("Thinking...")

        window.set_presence_text("Akiha is waiting nearby.")

        self.assertEqual(window._presence_label.text(), "Akiha is waiting nearby.")
        self.assertEqual(window._status_label.text(), "Thinking...")

    def test_blank_presence_text_uses_fallback(self) -> None:
        window = ChatWindow()

        window.set_presence_text("   ")

        self.assertEqual(window._presence_label.text(), "Akiha is nearby.")

    def test_voice_button_is_disabled_without_input_capability(self) -> None:
        window = ChatWindow()

        window.set_voice_state("idle")

        self.assertFalse(window._voice_button.isEnabled())
        self.assertEqual(window._voice_button.text(), "Talk")

    def test_voice_button_requests_listening_from_idle(self) -> None:
        window = ChatWindow()
        requested: list[bool] = []
        window.voice_listen_requested.connect(lambda: requested.append(True))
        window.set_voice_capabilities(input_enabled=True, output_enabled=False)
        window.set_voice_state("idle")

        window._voice_button.click()

        self.assertEqual(requested, [True])

    def test_voice_button_stops_recording_while_listening(self) -> None:
        window = ChatWindow()
        requested: list[bool] = []
        window.voice_listen_stop_requested.connect(lambda: requested.append(True))
        window.set_voice_capabilities(input_enabled=True, output_enabled=False)
        window.set_voice_state("listening", "input")

        window._voice_button.click()

        self.assertEqual(window._voice_button.text(), "Stop")
        self.assertEqual(requested, [True])

    def test_voice_button_cancels_only_the_active_operation(self) -> None:
        window = ChatWindow()
        input_cancels: list[bool] = []
        output_cancels: list[bool] = []
        window.voice_listen_cancel_requested.connect(lambda: input_cancels.append(True))
        window.voice_speak_stop_requested.connect(lambda: output_cancels.append(True))
        window.set_voice_capabilities(input_enabled=True, output_enabled=True)

        window.set_voice_state("thinking", "input")
        window._voice_button.click()
        window.set_voice_state("thinking", "output")
        window._voice_button.click()

        self.assertEqual(input_cancels, [True])
        self.assertEqual(output_cancels, [True])

    def test_voice_button_stops_speaking(self) -> None:
        window = ChatWindow()
        requested: list[bool] = []
        window.voice_speak_stop_requested.connect(lambda: requested.append(True))
        window.set_voice_capabilities(input_enabled=False, output_enabled=True)
        window.set_voice_state("speaking", "output")

        window._voice_button.click()

        self.assertEqual(window._voice_button.text(), "Stop voice")
        self.assertEqual(requested, [True])

    def test_replay_button_requests_last_spoken_response(self) -> None:
        window = ChatWindow()
        requested: list[bool] = []
        window.voice_replay_requested.connect(lambda: requested.append(True))
        window.set_voice_capabilities(input_enabled=False, output_enabled=True)
        window.set_voice_state("idle")
        window.set_voice_replay_available(True)

        window._voice_replay_button.click()

        self.assertTrue(window._voice_replay_button.isEnabled())
        self.assertEqual(requested, [True])

    def test_replay_button_requires_idle_voice_and_previous_speech(self) -> None:
        window = ChatWindow()
        window.set_voice_capabilities(input_enabled=False, output_enabled=True)
        window.set_voice_replay_available(True)

        window.set_voice_state("speaking", "output")
        self.assertFalse(window._voice_replay_button.isEnabled())

        window.set_voice_state("idle")
        self.assertTrue(window._voice_replay_button.isEnabled())

        window.set_voice_replay_available(False)
        self.assertFalse(window._voice_replay_button.isEnabled())

    def test_disabling_output_capability_disables_replay_button(self) -> None:
        window = ChatWindow()
        window.set_voice_capabilities(input_enabled=False, output_enabled=True)
        window.set_voice_state("idle")
        window.set_voice_replay_available(True)

        window.set_voice_capabilities(input_enabled=False, output_enabled=False)

        self.assertFalse(window._voice_replay_button.isEnabled())

    def test_chat_busy_state_disables_replay_button(self) -> None:
        window = ChatWindow()
        window.set_voice_capabilities(input_enabled=False, output_enabled=True)
        window.set_voice_state("idle")
        window.set_voice_replay_available(True)

        window.set_busy(True)

        self.assertFalse(window._voice_replay_button.isEnabled())

    def test_chat_busy_state_disables_voice_button(self) -> None:
        window = ChatWindow()
        window.set_voice_capabilities(input_enabled=True, output_enabled=True)
        window.set_voice_state("idle")

        window.set_busy(True)

        self.assertFalse(window._voice_button.isEnabled())

    def test_voice_transcript_is_inserted_without_being_sent(self) -> None:
        window = ChatWindow()
        submitted: list[str] = []
        window.message_submitted.connect(submitted.append)
        window._input.setText("Good morning")
        window._input.setCursorPosition(4)

        window.insert_voice_transcript(" おはよう ")

        self.assertEqual(window._input.text(), "Good おはよう morning")
        self.assertEqual(submitted, [])

    def test_voice_transcript_preview_is_visible_but_not_chat_history(self) -> None:
        window = ChatWindow()

        window.show_voice_transcript_preview("Recognized speech.")

        self.assertIn("Recognized speech.", window._voice_input_status.text())
        self.assertNotIn("Recognized speech.", window._history_view.toPlainText())

    def test_live_transcript_is_visible_but_not_chat_history_or_input(self) -> None:
        window = ChatWindow()

        window.show_live_voice_transcript("Words still changing.")

        self.assertIn("Words still changing.", window._voice_input_status.text())
        self.assertEqual(window._input.text(), "")
        self.assertNotIn("Words still changing.", window._history_view.toPlainText())

    def test_final_voice_transcript_can_be_submitted_automatically(self) -> None:
        window = ChatWindow()
        submitted: list[str] = []
        window.message_submitted.connect(submitted.append)

        window.submit_voice_transcript("Final recognized speech.")

        self.assertEqual(submitted, ["Final recognized speech."])
        self.assertEqual(window._input.text(), "")

    def test_voice_input_status_explains_how_to_finish_recording(self) -> None:
        window = ChatWindow()

        window.set_voice_input_status(
            "Listening... click Stop when you finish speaking."
        )

        self.assertEqual(
            window._voice_input_status.text(),
            "Listening... click Stop when you finish speaking.",
        )


if __name__ == "__main__":
    unittest.main()
