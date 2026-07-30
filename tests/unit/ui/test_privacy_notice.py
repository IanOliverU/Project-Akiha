"""Tests for the first-run privacy notice dialog."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialogButtonBox, QLabel

from project_akiha.ui.privacy_notice import PrivacyNoticeDialog


class PrivacyNoticeDialogTest(unittest.TestCase):
    """Verify required privacy information and acknowledgement."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_notice_describes_local_hosted_and_microphone_boundaries(self) -> None:
        dialog = PrivacyNoticeDialog()

        text = " ".join(label.text() for label in dialog.findChildren(QLabel))

        self.assertIn("Raw microphone audio", text)
        self.assertIn("Local processing", text)
        self.assertIn("Hosted processing", text)
        self.assertIn("encrypted", text)

    def test_acknowledge_button_accepts_dialog(self) -> None:
        dialog = PrivacyNoticeDialog()
        accepted: list[bool] = []
        dialog.accepted.connect(lambda: accepted.append(True))
        buttons = dialog.findChild(QDialogButtonBox)

        buttons.button(QDialogButtonBox.StandardButton.Ok).click()

        self.assertEqual(accepted, [True])


if __name__ == "__main__":
    unittest.main()
