"""Workspace and save/quit interactions through actual application composition."""

import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QMessageBox

from tests.unit.app import test_phase13b_composition as composition


class WorkspaceCompositionTest(unittest.TestCase):
    release_graph = composition.Phase13BCompositionTest.release_graph

    @classmethod
    def setUpClass(cls):
        composition.Phase13BCompositionTest.setUpClass()
        cls.app = composition.Phase13BCompositionTest.app

    def setUp(self):
        composition.Phase13BCompositionTest.setUp(self)
        self.settings = self.state["settings_window"]
        self.addCleanup(lambda: setattr(self.settings, "_draft_dirty", False))

    def test_workspace_routes_reuse_existing_pages_and_managers(self):
        identity = id(self.settings)
        self.window._destinations["music"].click()
        self.assertEqual(self.settings._tabs.currentIndex(), 8)
        self.window._destinations["utilities"].click()
        self.assertEqual(self.settings._tabs.currentIndex(), 9)
        self.assertEqual(id(self.state["settings_window"]), identity)
        self.window._destinations["memories"].click()
        self.assertTrue(self.state["memory_window"].isVisible())
        self.window._destinations["notifications"].click()
        self.assertTrue(self.state["notification_center_window"].isVisible())
        self.assertEqual(self.provider.prompts, [])

    def test_real_save_failure_retains_edits_without_claiming_persistence(self):
        before = self.settings._config
        self.settings._fps_input.setValue(42)
        with patch.object(
            self.state["user_config_store"],
            "save_config",
            side_effect=OSError("synthetic denied write"),
        ):
            self.assertFalse(self.settings._save())
        self.assertEqual(self.settings._config, before)
        self.assertTrue(self.settings._draft_dirty)
        self.assertEqual(self.settings._fps_input.value(), 42)
        self.assertIn("could not be saved", self.settings._save_status.text())

    def test_quit_cancel_preserves_settings_and_does_not_stop_runtime(self):
        self.settings._mark_unsaved()
        with (
            patch.object(
                QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel
            ),
            patch.object(self.app, "quit") as quit_app,
        ):
            self.state["request_application_quit"]()
            quit_app.assert_not_called()
        self.assertTrue(self.settings._draft_dirty)
        self.assertTrue(self.state["utility_timer_tick"].isActive())
