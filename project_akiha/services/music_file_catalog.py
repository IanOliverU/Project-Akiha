"""Local music references; registration neither reads audio nor grants access."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from project_akiha.config import MusicFilesConfig
from project_akiha.config.settings import MAX_MUSIC_FILES
from project_akiha.core.actions import ApprovedDirectory, ProtectedPathPolicy
from project_akiha.core.actions.passive_files import (
    PASSIVE_AUDIO_EXTENSIONS,
    PassiveFilePolicy,
)

MAX_MUSIC_DROP = 200
MAX_MUSIC_SCAN_ENTRIES = 4000
MAX_MUSIC_SCAN_DEPTH = 8


@dataclass(frozen=True, slots=True)
class MusicRegistration:
    config: MusicFilesConfig = field(repr=False)
    added: int
    duplicates: int
    rejected: int
    approval_roots: tuple[str, ...] = field(default=(), repr=False)
    limited: bool = False


class MusicFileCatalog:
    """Reuse protected-path and passive-audio rules for trusted local selections."""

    def __init__(self, path_policy: ProtectedPathPolicy) -> None:
        self.path_policy = path_policy
        self.audio_policy = PassiveFilePolicy(PASSIVE_AUDIO_EXTENSIONS)

    def validate(self, value: str) -> Path:
        if (
            not isinstance(value, str)
            or not 1 <= len(value) <= 1024
            or any(ord(c) < 32 for c in value)
        ):
            raise ValueError("Invalid local music file.")
        path = self.path_policy.validate_path(value)
        return self.audio_policy.validate_file(path)

    def register(
        self, config: MusicFilesConfig, paths: tuple[str, ...]
    ) -> MusicRegistration:
        if not isinstance(paths, tuple) or len(paths) > MAX_MUSIC_DROP:
            raise ValueError("Add at most 200 music files at a time.")
        registered = list(config.paths)
        seen = {p.casefold() for p in registered}
        approval_roots: dict[str, str] = {}
        added = duplicates = rejected = 0
        entries_remaining = MAX_MUSIC_SCAN_ENTRIES
        matches_remaining = MAX_MUSIC_DROP
        limited = False

        def accept(value: str, root: str | None = None) -> None:
            nonlocal added, duplicates, rejected, matches_remaining, limited
            try:
                path = str(self.validate(value))
            except (OSError, ValueError):
                rejected += 1
                return
            if matches_remaining == 0:
                limited = True
                return
            matches_remaining -= 1
            if path.casefold() in seen:
                duplicates += 1
            elif len(registered) >= MAX_MUSIC_FILES:
                rejected += 1
                return
            else:
                registered.append(path)
                seen.add(path.casefold())
                added += 1
            approved_root = root or str(Path(path).parent)
            approval_roots[approved_root.casefold()] = approved_root

        def scan(folder: Path, root: str, depth: int) -> None:
            nonlocal entries_remaining, limited, rejected
            if matches_remaining == 0 or entries_remaining == 0:
                limited = True
                return
            try:
                folder = self.path_policy.validate_path(str(folder))
                with os.scandir(folder) as iterator:
                    entries = []
                    for entry in iterator:
                        if entries_remaining == 0:
                            limited = True
                            break
                        entries_remaining -= 1
                        entries.append(entry)
                for entry in sorted(entries, key=lambda item: item.name.casefold()):
                    if matches_remaining == 0:
                        limited = True
                        break
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if depth < MAX_MUSIC_SCAN_DEPTH:
                                scan(Path(entry.path), root, depth + 1)
                            else:
                                limited = True
                        elif (
                            entry.is_file(follow_symlinks=False)
                            and Path(entry.name).suffix.casefold()
                            in PASSIVE_AUDIO_EXTENSIONS
                        ):
                            accept(entry.path, root)
                    except OSError:
                        rejected += 1
            except (OSError, ValueError):
                rejected += 1

        for value in paths:
            if (
                not isinstance(value, str)
                or not 1 <= len(value) <= 1024
                or any(ord(c) < 32 for c in value)
            ):
                rejected += 1
                continue
            try:
                path = self.path_policy.validate_path(value)
                if path.is_dir():
                    scan(path, str(path), 0)
                else:
                    accept(value)
            except (OSError, ValueError, TypeError, AttributeError):
                rejected += 1
        return MusicRegistration(
            MusicFilesConfig(tuple(registered)),
            added,
            duplicates,
            rejected,
            tuple(approval_roots.values()),
            limited,
        )

    def status(self, path: str, directories: tuple[ApprovedDirectory, ...]) -> str:
        try:
            self.validate(path)
        except (OSError, ValueError):
            return "Missing or unavailable"
        if not any(
            root.can_open
            and root.is_available
            and self.path_policy.is_within(path, root.root)
            for root in directories
        ):
            return "Needs folder approval"
        return "Ready"
