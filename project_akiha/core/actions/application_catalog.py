"""Trusted discovery of the small allowlisted desktop application catalog."""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

_WINDOWS_REPARSE_POINT = 0x400


@dataclass(frozen=True, slots=True)
class InstalledApplication:
    """One catalog entry with an optional trusted executable path."""

    application_id: str
    display_name: str
    executable: Path | None

    @property
    def is_available(self) -> bool:
        """Return whether discovery found a usable executable."""
        return self.executable is not None


class ApplicationCatalog:
    """Discover only known GUI applications from application-owned paths."""

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environment = MappingProxyType(
            dict(environ if environ is not None else os.environ)
        )

    @property
    def application_ids(self) -> tuple[str, ...]:
        """Return the stable catalog identifiers."""
        return tuple(spec[0] for spec in _APPLICATION_SPECS)

    def discover(self) -> tuple[InstalledApplication, ...]:
        """Return every catalog entry with its current availability."""
        return tuple(
            self.resolve(application_id) for application_id in self.application_ids
        )

    def resolve(self, application_id: str) -> InstalledApplication:
        """Resolve one known identifier without accepting an arbitrary path."""
        normalized = application_id.strip().casefold()
        try:
            display_name, candidates = next(
                (name, resolver(self._environment))
                for identifier, name, resolver in _APPLICATION_SPECS
                if identifier == normalized
            )
        except StopIteration as error:
            raise ValueError("application is not in the trusted catalog.") from error

        executable = next(
            (
                candidate.resolve()
                for candidate in candidates
                if _is_safe_executable(candidate)
            ),
            None,
        )
        return InstalledApplication(normalized, display_name, executable)


def _application_paths(
    environment: Mapping[str, str],
    *parts: tuple[str, ...],
) -> tuple[Path, ...]:
    roots = tuple(
        Path(value)
        for name in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)")
        if (value := _environment_value(environment, name))
    )
    return tuple(
        root.joinpath(*relative_parts) for root in roots for relative_parts in parts
    )


def _chrome_candidates(environment: Mapping[str, str]) -> tuple[Path, ...]:
    candidates = list(
        _application_paths(
            environment,
            ("Google", "Chrome", "Application", "chrome.exe"),
        )
    )
    local_app_data = _environment_value(environment, "LOCALAPPDATA")
    if local_app_data:
        candidates.append(
            Path(local_app_data) / "Google" / "Chrome" / "Application" / "chrome.exe"
        )
    return tuple(candidates)


def _discord_candidates(environment: Mapping[str, str]) -> tuple[Path, ...]:
    local_app_data = _environment_value(environment, "LOCALAPPDATA")
    if not local_app_data:
        return ()
    root = Path(local_app_data) / "Discord"
    return tuple(root.glob("app-*/Discord.exe")) + (root / "Discord.exe",)


def _spotify_candidates(environment: Mapping[str, str]) -> tuple[Path, ...]:
    candidates: list[Path] = []
    for name in ("APPDATA", "LOCALAPPDATA"):
        value = _environment_value(environment, name)
        if value:
            candidates.append(Path(value) / "Spotify" / "Spotify.exe")
    return tuple(candidates)


def _vscode_candidates(environment: Mapping[str, str]) -> tuple[Path, ...]:
    candidates = list(
        _application_paths(
            environment,
            ("Microsoft VS Code", "Code.exe"),
        )
    )
    local_app_data = _environment_value(environment, "LOCALAPPDATA")
    if local_app_data:
        candidates.append(
            Path(local_app_data) / "Programs" / "Microsoft VS Code" / "Code.exe"
        )
    return tuple(candidates)


def _vlc_candidates(environment: Mapping[str, str]) -> tuple[Path, ...]:
    return _application_paths(
        environment,
        ("VideoLAN", "VLC", "vlc.exe"),
    )


_APPLICATION_SPECS = (
    ("chrome", "Google Chrome", _chrome_candidates),
    ("discord", "Discord", _discord_candidates),
    ("spotify", "Spotify", _spotify_candidates),
    ("vlc", "VLC media player", _vlc_candidates),
    ("vscode", "Visual Studio Code", _vscode_candidates),
)


def _environment_value(environment: Mapping[str, str], name: str) -> str | None:
    """Read a Windows environment variable without depending on key casing."""
    expected = name.casefold()
    return next(
        (
            value
            for key, value in environment.items()
            if key.casefold() == expected and value
        ),
        None,
    )


def _is_safe_executable(path: Path) -> bool:
    """Accept only existing regular non-link files from catalog paths."""
    try:
        details = path.lstat()
    except OSError:
        return False
    attributes = getattr(details, "st_file_attributes", 0)
    return (
        stat.S_ISREG(details.st_mode)
        and not stat.S_ISLNK(details.st_mode)
        and not attributes & _WINDOWS_REPARSE_POINT
    )
