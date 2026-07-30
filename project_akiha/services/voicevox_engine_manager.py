"""Lifecycle management for an optional local VOICEVOX Engine process."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from project_akiha.config import VoiceConfig


class ManagedEngineProcess(Protocol):
    """Process operations needed by the engine manager."""

    def poll(self) -> int | None:
        """Return the exit code, or None while running."""

    def terminate(self) -> None:
        """Request graceful termination."""

    def wait(self, timeout: float | None = None) -> int:
        """Wait for process exit."""

    def kill(self) -> None:
        """Force process termination."""


@dataclass(frozen=True, slots=True)
class VoiceVoxEngineStatus:
    """A user-facing engine management result."""

    state: str
    detail: str
    is_error: bool = False


ProcessFactory = Callable[[Sequence[str], Path], ManagedEngineProcess]
EndpointProbe = Callable[[str], bool]


class VoiceVoxEngineManager:
    """Start and stop only the local VOICEVOX Engine owned by Akiha."""

    def __init__(
        self,
        project_root: Path,
        *,
        process_factory: ProcessFactory | None = None,
        endpoint_probe: EndpointProbe | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._project_root = project_root
        self._process_factory = process_factory or _start_hidden_process
        self._endpoint_probe = endpoint_probe or _probe_voicevox_endpoint
        self._environment = environment if environment is not None else os.environ
        self._process: ManagedEngineProcess | None = None
        self._launch_signature: tuple[Path, str, int] | None = None
        self._stop_on_exit = True

    @property
    def owns_running_process(self) -> bool:
        """Return whether Akiha owns a currently running engine."""
        return self._process is not None and self._process.poll() is None

    def apply_config(self, config: VoiceConfig) -> VoiceVoxEngineStatus:
        """Apply engine settings and start or stop the managed process."""
        self._stop_on_exit = config.output_engine_stop_on_exit
        if not _should_manage_engine(config):
            self.stop()
            return VoiceVoxEngineStatus(
                "disabled",
                "Automatic VOICEVOX Engine management is disabled.",
            )

        endpoint = _local_endpoint(config.output_base_url)
        if endpoint is None:
            self.stop()
            return VoiceVoxEngineStatus(
                "unsupported_endpoint",
                "Automatic engine start only supports a local VOICEVOX URL.",
                True,
            )

        if self._endpoint_probe(config.output_base_url):
            if self.owns_running_process:
                return VoiceVoxEngineStatus(
                    "running",
                    "The managed VOICEVOX Engine is running.",
                )
            return VoiceVoxEngineStatus(
                "external",
                "VOICEVOX Engine is already running outside Project Akiha.",
            )

        executable = self._resolve_executable(config.output_engine_path)
        if executable is None:
            self.stop()
            return VoiceVoxEngineStatus(
                "missing",
                "Select the standalone VOICEVOX Engine executable.",
                True,
            )

        host, port = endpoint
        signature = (executable, host, port)
        if self.owns_running_process and self._launch_signature == signature:
            return VoiceVoxEngineStatus(
                "starting",
                "The managed VOICEVOX Engine is still starting.",
            )
        self.stop()

        command = (
            str(executable),
            "--host",
            host,
            "--port",
            str(port),
        )
        try:
            self._process = self._process_factory(command, executable.parent)
        except OSError:
            self._process = None
            self._launch_signature = None
            return VoiceVoxEngineStatus(
                "failed",
                "The standalone VOICEVOX Engine could not be started.",
                True,
            )

        self._launch_signature = signature
        return VoiceVoxEngineStatus(
            "starting",
            "Starting the managed VOICEVOX Engine in the background.",
        )

    def refresh_status(self, base_url: str) -> VoiceVoxEngineStatus:
        """Return current endpoint and owned-process status."""
        if self._endpoint_probe(base_url):
            detail = (
                "The managed VOICEVOX Engine is running."
                if self.owns_running_process
                else "VOICEVOX Engine is already running outside Project Akiha."
            )
            return VoiceVoxEngineStatus("running", detail)
        if self.owns_running_process:
            return VoiceVoxEngineStatus(
                "starting",
                "The managed VOICEVOX Engine is still starting.",
            )
        return VoiceVoxEngineStatus(
            "unavailable",
            "VOICEVOX Engine is not reachable.",
            True,
        )

    def stop(self, timeout_seconds: float = 5.0) -> bool:
        """Stop the owned process without touching an external engine."""
        process = self._process
        self._process = None
        self._launch_signature = None
        if process is None or process.poll() is not None:
            return True
        try:
            process.terminate()
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=timeout_seconds)
        except OSError:
            return False
        return True

    def shutdown(self) -> bool:
        """Apply the configured exit policy to the owned process."""
        if not self._stop_on_exit:
            self._process = None
            self._launch_signature = None
            return True
        return self.stop()

    def _resolve_executable(self, configured_path: str) -> Path | None:
        configured = configured_path.strip()
        if configured:
            path = Path(configured).expanduser()
            if not path.is_absolute():
                path = self._project_root / path
            return path.resolve() if path.is_file() else None

        environment_path = self._environment.get("VOICEVOX_ENGINE_PATH", "").strip()
        candidates = []
        if environment_path:
            candidates.append(Path(environment_path).expanduser())
        local_app_data = self._environment.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            candidates.append(
                Path(local_app_data) / "Programs" / "VOICEVOX" / "vv-engine" / "run.exe"
            )
        candidates.extend(
            (
                self._project_root / "voicevox-engine" / "run.exe",
                self._project_root / "tools" / "voicevox-engine" / "run.exe",
                Path.home() / "voicevox-engine" / "run.exe",
            )
        )
        command_path = shutil.which("voicevox_engine")
        if command_path:
            candidates.append(Path(command_path))

        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        return None


def _should_manage_engine(config: VoiceConfig) -> bool:
    return (
        config.enabled
        and config.output_provider == "voicevox"
        and config.output_engine_auto_start
    )


def _local_endpoint(base_url: str) -> tuple[str, int] | None:
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "http" or host not in {"127.0.0.1", "localhost", "::1"}:
        return None
    return host, parsed.port or 80


def _probe_voicevox_endpoint(base_url: str) -> bool:
    request = Request(
        f"{base_url.rstrip('/')}/version",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=0.5) as response:
            return 200 <= response.status < 300
    except (HTTPError, URLError, TimeoutError, OSError):
        return False


def _start_hidden_process(
    command: Sequence[str],
    working_directory: Path,
) -> ManagedEngineProcess:
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    startup_info = None
    if os.name == "nt":
        startup_info = subprocess.STARTUPINFO()
        startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup_info.wShowWindow = subprocess.SW_HIDE
    return subprocess.Popen(
        tuple(command),
        cwd=working_directory,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
        startupinfo=startup_info,
    )
