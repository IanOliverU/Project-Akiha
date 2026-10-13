"""Historical populated profiles detect migration, preservation and schema gaps."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from project_akiha.core.appearance import load_appearance_registry
from project_akiha.database.migrator import DatabaseMigrator
from project_akiha.tools.verify_upgrade_fixture import create_fixture, verify_fixture


class UpgradeFixtureTest(unittest.TestCase):
    def test_fixture_appearance_remains_valid_for_normal_startup(self):
        root = Path(__file__).resolve().parents[3]
        registry = load_appearance_registry(root / "assets/animations/appearances.toml")
        with tempfile.TemporaryDirectory() as temp:
            profile = Path(temp) / "Akiha"
            create_fixture(profile, 14)
            with closing(sqlite3.connect(profile / "akiha.sqlite3")) as connection:
                selection = connection.execute(
                    "SELECT appearance_id FROM pet_appearance_selection"
                ).fetchone()[0]
            self.assertEqual(selection, registry.default_appearance_id.value)
            self.assertTrue(
                registry.manifest_path(registry.default_appearance_id).is_file()
            )

    def test_populated_prior_versions_upgrade_and_restart(self):
        for version in (14, 15):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as temp:
                profile = Path(temp) / "Akiha"
                create_fixture(profile, version)
                with self.assertRaises(AssertionError):
                    verify_fixture(profile)  # Old schema must fail target acceptance.
                migrator = DatabaseMigrator(profile / "akiha.sqlite3")
                migrator.apply_pending()
                verify_fixture(profile)
                migrator.apply_pending()
                verify_fixture(profile)

    def test_existing_profile_is_rejected_without_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            profile = Path(temp)
            marker = profile / "owner-data"
            marker.write_text("untouched")
            with self.assertRaises(FileExistsError):
                create_fixture(profile, 14)
            self.assertEqual(marker.read_text(), "untouched")
            self.assertEqual(list(profile.iterdir()), [marker])

    def test_missing_permissions_or_changed_grant_fails(self):
        for damage in (
            "DROP TABLE assistant_action_audit",
            "UPDATE assistant_action_permissions SET revoked_at='changed' WHERE id=104",
        ):
            with self.subTest(damage=damage), tempfile.TemporaryDirectory() as temp:
                profile = Path(temp) / "Akiha"
                create_fixture(profile, 14)
                DatabaseMigrator(profile / "akiha.sqlite3").apply_pending()
                with closing(sqlite3.connect(profile / "akiha.sqlite3")) as connection:
                    connection.execute(damage)
                    connection.commit()
                with self.assertRaises(AssertionError):
                    verify_fixture(profile)
