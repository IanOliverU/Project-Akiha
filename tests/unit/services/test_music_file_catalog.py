"""Registration retains local references without changing files or authority."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from project_akiha.config import AppConfig, MusicFilesConfig, load_config
from project_akiha.core.actions import ProtectedPathPolicy
from project_akiha.services.config_store import UserConfigStore
from project_akiha.services.music_file_catalog import MusicFileCatalog


class MusicFileCatalogTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.catalog = MusicFileCatalog(ProtectedPathPolicy())

    def file(self, name):
        path = self.root / name
        path.write_bytes(b"synthetic audio; never decoded or played")
        return path

    def test_register_passive_audio_references_and_deduplicate(self):
        paths = tuple(
            self.file("song" + ext) for ext in (".mp3", ".wav", ".flac", ".ogg", ".m4a")
        )
        before = {p: p.read_bytes() for p in paths}
        result = self.catalog.register(
            MusicFilesConfig(), tuple(map(str, paths)) + (str(paths[0]),)
        )
        self.assertEqual((result.added, result.duplicates, result.rejected), (5, 1, 0))
        self.assertEqual(result.config.paths, tuple(map(str, paths)))
        self.assertEqual(before, {p: p.read_bytes() for p in paths})
        self.assertNotIn(str(paths[0]), repr(result))

    def test_reject_active_missing_remote_and_nonabsolute_inputs(self):
        active = self.file("active.exe")
        unsupported = self.file("document.txt")
        result = self.catalog.register(
            MusicFilesConfig(),
            (
                str(active),
                str(unsupported),
                str(self.root / "missing.mp3"),
                "relative.mp3",
                "file:///C:/secret.mp3",
                r"\\server\share\song.mp3",
                "%2FC%3A%2Fsong.mp3",
                "\x00secret.mp3",
            ),
        )
        self.assertEqual((result.added, result.rejected), (0, 8))
        self.assertEqual(result.config.paths, ())

    def test_protected_root_is_rejected_without_granting_access(self):
        song = self.file("secret.mp3")
        catalog = MusicFileCatalog(ProtectedPathPolicy(protected_roots=(self.root,)))
        result = catalog.register(MusicFilesConfig(), (str(song),))
        self.assertEqual(result.rejected, 1)
        self.assertEqual(self.catalog.status(str(song), ()), "Needs folder approval")

    def test_literal_percent_filename_is_not_decoded_into_a_different_path(self):
        song = self.file("literal%2F name.mp3")
        result = self.catalog.register(MusicFilesConfig(), (str(song),))
        self.assertEqual(result.config.paths, (str(song),))
        self.assertFalse((self.root / "literal" / " name.mp3").exists())

    def test_config_roundtrip_unicode_spaces_percent_and_missing_reference(self):
        song = self.file("音樂 private %25.mp3")
        config = AppConfig().with_music_files(MusicFilesConfig((str(song),)))
        store = UserConfigStore(self.root / "user.toml")
        store.save_config(config)
        song.unlink()
        loaded = load_config(config_path=store.config_path)
        self.assertEqual(loaded.music_files, config.music_files)
        self.assertNotIn("private", repr(loaded.music_files))
        self.assertEqual(self.catalog.status(str(song), ()), "Missing or unavailable")

    def test_registration_limits_and_config_validation_fail_closed(self):
        song = self.file("song.mp3")
        with self.assertRaises(ValueError):
            self.catalog.register(MusicFilesConfig(), (str(song),) * 201)
        full = MusicFilesConfig(tuple(str(self.root / f"{i}.mp3") for i in range(1000)))
        self.assertEqual(self.catalog.register(full, (str(song),)).rejected, 1)
        for paths in (
            ("relative.mp3",),
            (str(song), str(song).upper()),
            (str(song) + "\n",),
            full.paths + (str(song),),
        ):
            with self.subTest(paths_count=len(paths)), self.assertRaises(ValueError):
                MusicFilesConfig(paths)

    def test_album_folder_collects_nested_audio_and_approves_only_selected_root(self):
        album = self.root / "Album"
        disc = album / "Disc 2"
        disc.mkdir(parents=True)
        for path in (album / "First.mp3", disc / "Second.FLAC", album / "cover.jpg"):
            path.write_bytes(b"synthetic")
        result = self.catalog.register(MusicFilesConfig(), (str(album),))
        self.assertEqual(
            set(result.config.paths),
            {str(album / "First.mp3"), str(disc / "Second.FLAC")},
        )
        self.assertEqual(result.approval_roots, (str(album),))
        self.assertEqual(result.added, 2)
        self.assertFalse(result.limited)
        self.assertNotIn(str(album), repr(result))

    def test_empty_and_non_audio_folders_do_not_request_approval(self):
        self.file("album.zip")
        self.file("launcher.exe")
        result = self.catalog.register(MusicFilesConfig(), (str(self.root),))
        self.assertEqual(result.config.paths, ())
        self.assertEqual(result.approval_roots, ())

    def test_folder_scan_bounds_matches_entries_and_depth(self):
        for i in range(4):
            self.file(f"song{i}.mp3")
        with patch("project_akiha.services.music_file_catalog.MAX_MUSIC_DROP", 2):
            result = self.catalog.register(MusicFilesConfig(), (str(self.root),))
        self.assertEqual(result.added, 2)
        self.assertTrue(result.limited)
        with patch(
            "project_akiha.services.music_file_catalog.MAX_MUSIC_SCAN_ENTRIES", 2
        ):
            result = self.catalog.register(MusicFilesConfig(), (str(self.root),))
        self.assertEqual(result.added, 2)
        self.assertTrue(result.limited)
        child = self.root / "nested"
        child.mkdir()
        (child / "too deep.mp3").write_bytes(b"synthetic")
        with patch("project_akiha.services.music_file_catalog.MAX_MUSIC_SCAN_DEPTH", 0):
            result = self.catalog.register(MusicFilesConfig(), (str(self.root),))
        self.assertNotIn(str(child / "too deep.mp3"), result.config.paths)
        self.assertTrue(result.limited)

    def test_link_entries_are_not_followed(self):
        entry = MagicMock()
        entry.name = "link"
        entry.is_symlink.return_value = True
        scanner = MagicMock()
        scanner.__enter__.return_value = iter((entry,))
        with patch(
            "project_akiha.services.music_file_catalog.os.scandir", return_value=scanner
        ):
            result = self.catalog.register(MusicFilesConfig(), (str(self.root),))
        self.assertEqual(result.approval_roots, ())
        entry.is_dir.assert_not_called()
        entry.is_file.assert_not_called()

    def test_protected_subfolder_is_not_scanned(self):
        blocked = self.root / "Blocked"
        blocked.mkdir()
        (blocked / "Private.mp3").write_bytes(b"synthetic")
        safe = self.file("Allowed.mp3")
        catalog = MusicFileCatalog(ProtectedPathPolicy(protected_roots=(blocked,)))
        result = catalog.register(MusicFilesConfig(), (str(self.root),))
        self.assertEqual(result.config.paths, (str(safe),))
        self.assertEqual(result.rejected, 1)


if __name__ == "__main__":
    unittest.main()
