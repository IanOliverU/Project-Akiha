"""Lifecycle management for the local GPT-SoVITS API process."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from threading import RLock
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from project_akiha.config import VoiceConfig


class ManagedEngineProcess:
    """Process protocol used by the GPT-SoVITS manager."""

    def poll(self) -> int | None:
        raise NotImplementedError

    def terminate(self) -> None:
        raise NotImplementedError

    def wait(self, timeout: float | None = None) -> int:
        raise NotImplementedError

    def kill(self) -> None:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class GptSoVitsEngineStatus:
    """A user-facing GPT-SoVITS lifecycle result."""

    state: str
    detail: str
    is_error: bool = False


class GptSoVitsHealthState(StrEnum):
    """Stable runtime-health vocabulary used by Phase 12 diagnostics."""

    STARTING = "starting"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    RECOVERING = "recovering"


ProcessFactory = Callable[
    [Sequence[str], Path, Mapping[str, str]],
    ManagedEngineProcess,
]
EndpointProbe = Callable[[str], bool]


@dataclass(frozen=True, slots=True)
class _GptSoVitsRuntime:
    python_executable: Path
    source_dir: Path
    config_path: Path
    launcher_path: Path
    nltk_data_dir: Path | None


class GptSoVitsEngineManager:
    """Start and stop only the GPT-SoVITS process owned by Akiha."""

    def __init__(
        self,
        project_root: Path,
        *,
        process_factory: ProcessFactory | None = None,
        endpoint_probe: EndpointProbe | None = None,
        environment: Mapping[str, str] | None = None,
        maximum_recovery_attempts: int = 3,
        recovery_backoff_seconds: float = 2.0,
    ) -> None:
        if maximum_recovery_attempts < 1:
            raise ValueError("maximum_recovery_attempts must be positive.")
        if recovery_backoff_seconds <= 0:
            raise ValueError("recovery_backoff_seconds must be positive.")
        self._project_root = project_root
        self._process_factory = process_factory or _start_hidden_process
        self._endpoint_probe = endpoint_probe or _probe_gpt_sovits_endpoint
        self._environment = environment if environment is not None else os.environ
        self._process: ManagedEngineProcess | None = None
        self._launch_signature: tuple[Path, Path, str, int] | None = None
        self._stop_on_exit = True
        self._maximum_recovery_attempts = maximum_recovery_attempts
        self._recovery_backoff_seconds = recovery_backoff_seconds
        self._recovery_attempts = 0
        self._consecutive_health_failures = 0
        self._next_recovery_at = 0.0
        self._lock = RLock()

    @property
    def owns_running_process(self) -> bool:
        """Return whether Akiha owns a running GPT-SoVITS process."""
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def apply_config(self, config: VoiceConfig) -> GptSoVitsEngineStatus:
        """Start GPT-SoVITS for the active local Akiha voice configuration."""
        with self._lock:
            return self._apply_config(config)

    def _apply_config(self, config: VoiceConfig) -> GptSoVitsEngineStatus:
        self._stop_on_exit = config.output_engine_stop_on_exit
        if not config.enabled or config.output_provider != "gpt-sovits":
            self.stop()
            return GptSoVitsEngineStatus(
                "disabled",
                "Automatic GPT-SoVITS management is disabled.",
            )

        endpoint = _local_endpoint(config.output_base_url)
        if endpoint is None:
            self.stop()
            return GptSoVitsEngineStatus(
                "unsupported_endpoint",
                "Automatic GPT-SoVITS start only supports a local HTTP URL.",
                True,
            )

        if self._endpoint_probe(config.output_base_url):
            detail = (
                "The managed GPT-SoVITS API is running."
                if self.owns_running_process
                else "GPT-SoVITS API is already running outside Project Akiha."
            )
            return GptSoVitsEngineStatus("running", detail)

        if not config.output_engine_auto_start:
            self.stop()
            return GptSoVitsEngineStatus(
                "disabled",
                "Automatic GPT-SoVITS start is disabled.",
            )

        runtime = self._resolve_runtime()
        if runtime is None:
            self.stop()
            return GptSoVitsEngineStatus(
                "missing",
                "Install the isolated GPT-SoVITS runtime before starting voice output.",
                True,
            )

        python_executable = runtime.python_executable
        source_dir = runtime.source_dir
        config_path = runtime.config_path
        host, port = endpoint
        signature = (python_executable, source_dir, host, port)
        if self.owns_running_process and self._launch_signature == signature:
            return GptSoVitsEngineStatus(
                "starting",
                "The managed GPT-SoVITS API is still starting.",
            )
        self.stop()

        command = (
            str(python_executable),
            str(runtime.launcher_path),
            "-a",
            host,
            "-p",
            str(port),
            "-c",
            config_path.relative_to(source_dir).as_posix(),
        )
        environment = self._process_environment(runtime.nltk_data_dir)
        try:
            self._process = self._process_factory(command, source_dir, environment)
        except OSError:
            self._process = None
            self._launch_signature = None
            return GptSoVitsEngineStatus(
                "failed",
                "The local GPT-SoVITS API could not be started.",
                True,
            )

        self._launch_signature = signature
        return GptSoVitsEngineStatus(
            "starting",
            "Starting the managed GPT-SoVITS API in the background.",
        )

    def refresh_status(self, base_url: str) -> GptSoVitsEngineStatus:
        """Return current endpoint and owned-process status."""
        with self._lock:
            return self._refresh_status(base_url)

    def _refresh_status(self, base_url: str) -> GptSoVitsEngineStatus:
        if self._endpoint_probe(base_url):
            detail = (
                "The managed GPT-SoVITS API is running."
                if self.owns_running_process
                else "GPT-SoVITS API is already running outside Project Akiha."
            )
            return GptSoVitsEngineStatus("running", detail)
        if self.owns_running_process:
            return GptSoVitsEngineStatus(
                "starting",
                "The managed GPT-SoVITS API is still loading its models.",
            )
        return GptSoVitsEngineStatus(
            "unavailable",
            "GPT-SoVITS API is not reachable.",
            True,
        )

    @property
    def recovery_attempts(self) -> int:
        """Return the current bounded recovery-attempt count."""
        with self._lock:
            return self._recovery_attempts

    def monitor_and_recover(
        self,
        config: VoiceConfig,
        *,
        monotonic_now: float | None = None,
    ) -> GptSoVitsEngineStatus:
        """Probe health and recover a failed managed runtime within fixed bounds."""
        with self._lock:
            return self._monitor_and_recover(config, monotonic_now=monotonic_now)

    def _monitor_and_recover(
        self,
        config: VoiceConfig,
        *,
        monotonic_now: float | None,
    ) -> GptSoVitsEngineStatus:
        if not config.enabled or config.output_provider != "gpt-sovits":
            self._reset_health_tracking()
            return GptSoVitsEngineStatus(
                GptSoVitsHealthState.UNAVAILABLE.value,
                "GPT-SoVITS voice output is disabled.",
            )

        if self._endpoint_probe(config.output_base_url):
            self._reset_health_tracking()
            return GptSoVitsEngineStatus(
                GptSoVitsHealthState.HEALTHY.value,
                (
                    "The managed GPT-SoVITS API is healthy."
                    if self.owns_running_process
                    else "The external GPT-SoVITS API is healthy."
                ),
            )

        self._consecutive_health_failures += 1
        now = time.monotonic() if monotonic_now is None else monotonic_now
        if self.owns_running_process and self._consecutive_health_failures <= 2:
            return GptSoVitsEngineStatus(
                GptSoVitsHealthState.DEGRADED.value,
                "GPT-SoVITS did not answer its health probe; Akiha remains available.",
                True,
            )
        if not config.output_engine_auto_start:
            return GptSoVitsEngineStatus(
                GptSoVitsHealthState.UNAVAILABLE.value,
                "GPT-SoVITS API is unavailable and automatic recovery is disabled.",
                True,
            )
        if self._recovery_attempts >= self._maximum_recovery_attempts:
            return GptSoVitsEngineStatus(
                GptSoVitsHealthState.UNAVAILABLE.value,
                "GPT-SoVITS recovery limit was reached; use Retry in Settings.",
                True,
            )
        if now < self._next_recovery_at:
            return GptSoVitsEngineStatus(
                GptSoVitsHealthState.DEGRADED.value,
                "GPT-SoVITS recovery is waiting for its bounded backoff.",
                True,
            )

        self.stop()
        self._recovery_attempts += 1
        self._next_recovery_at = now + min(
            self._recovery_backoff_seconds * (2 ** (self._recovery_attempts - 1)),
            30.0,
        )
        status = self.apply_config(config)
        if status.state == "starting":
            return GptSoVitsEngineStatus(
                GptSoVitsHealthState.RECOVERING.value,
                "Restarting the managed GPT-SoVITS API in the background.",
            )
        return GptSoVitsEngineStatus(
            GptSoVitsHealthState.UNAVAILABLE.value,
            status.detail,
            True,
        )

    def reset_recovery(self) -> None:
        """Allow an explicit user-requested recovery cycle."""
        with self._lock:
            self._reset_health_tracking()

    def _reset_health_tracking(self) -> None:
        self._recovery_attempts = 0
        self._consecutive_health_failures = 0
        self._next_recovery_at = 0.0

    def wait_until_ready(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 60.0,
        poll_interval_seconds: float = 0.5,
    ) -> bool:
        """Wait for an owned process to expose its endpoint within a fixed bound."""
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be greater than zero.")

        deadline = time.monotonic() + timeout_seconds
        while True:
            if self._endpoint_probe(base_url):
                return True
            if not self.owns_running_process:
                return False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(poll_interval_seconds, remaining))

    def stop(self, timeout_seconds: float = 5.0) -> bool:
        """Stop the owned process without touching an external API process."""
        with self._lock:
            return self._stop(timeout_seconds)

    def _stop(self, timeout_seconds: float) -> bool:
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
        """Apply the configured exit policy to the owned API process."""
        with self._lock:
            if not self._stop_on_exit:
                self._process = None
                self._launch_signature = None
                return True
            return self._stop(5.0)

    def _resolve_runtime(self) -> _GptSoVitsRuntime | None:
        support_roots = self._support_roots()
        source_candidates = []
        configured_source = self._environment.get("AKIHA_GPT_SOVITS_SOURCE", "").strip()
        if configured_source:
            source_candidates.append(Path(configured_source).expanduser())
        source_candidates.extend(root / ".gpt-sovits-src" for root in support_roots)

        python_candidates = []
        configured_python = self._environment.get("AKIHA_GPT_SOVITS_PYTHON", "").strip()
        if configured_python:
            python_candidates.append(Path(configured_python).expanduser())
        for root in support_roots:
            python_candidates.extend(
                (
                    root / ".gpt-sovits-venv" / "Scripts" / "python.exe",
                    root / ".gpt-sovits-venv" / "bin" / "python",
                )
            )

        launcher_candidates = []
        configured_launcher = self._environment.get(
            "AKIHA_GPT_SOVITS_LAUNCHER", ""
        ).strip()
        if configured_launcher:
            launcher_candidates.append(Path(configured_launcher).expanduser())
        launcher_candidates.extend(
            root / "scripts" / "run_gpt_sovits_api.py" for root in support_roots
        )
        launcher_path = next(
            (
                candidate.resolve()
                for candidate in launcher_candidates
                if candidate.is_file()
            ),
            None,
        )
        if launcher_path is None:
            return None

        command_python = shutil.which("python3.10") or shutil.which("python3")
        if command_python:
            python_candidates.append(Path(command_python))

        for source in source_candidates:
            source = source.resolve()
            api_path = source / "api_v2.py"
            config_path = source / "GPT_SoVITS" / "configs" / "tts_infer.yaml"
            if not api_path.is_file() or not config_path.is_file():
                continue
            for python_executable in python_candidates:
                python_executable = python_executable.resolve()
                if python_executable.is_file():
                    venv_root = python_executable.parent.parent
                    nltk_data_dir = venv_root / "nltk_data"
                    return _GptSoVitsRuntime(
                        python_executable=python_executable,
                        source_dir=source,
                        config_path=config_path,
                        launcher_path=launcher_path,
                        nltk_data_dir=(
                            nltk_data_dir if nltk_data_dir.is_dir() else None
                        ),
                    )
        return None

    def _support_roots(self) -> tuple[Path, ...]:
        """Return bounded locations that may own the external voice runtime."""
        return gpt_sovits_support_roots(self._project_root, self._environment)

    def _process_environment(self, nltk_data_dir: Path | None) -> dict[str, str]:
        environment = dict(self._environment)
        if nltk_data_dir is not None:
            environment["NLTK_DATA"] = str(nltk_data_dir)
        ffmpeg_bin = _resolve_ffmpeg_bin(environment)
        if ffmpeg_bin is not None:
            environment["AKIHA_FFMPEG_BIN"] = str(ffmpeg_bin)
            path_entries = environment.get("PATH", "").split(os.pathsep)
            if str(ffmpeg_bin) not in path_entries:
                environment["PATH"] = os.pathsep.join(
                    [str(ffmpeg_bin), *[entry for entry in path_entries if entry]]
                )
        environment["PYTHONUTF8"] = "1"
        return environment


def _local_endpoint(base_url: str) -> tuple[str, int] | None:
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "http" or host not in {"127.0.0.1", "localhost", "::1"}:
        return None
    return host, parsed.port or 80


def gpt_sovits_support_roots(
    project_root: Path,
    environment: Mapping[str, str] | None = None,
) -> tuple[Path, ...]:
    """Return bounded external roots shared by runtime and reference discovery."""
    env = environment if environment is not None else os.environ
    candidates = [project_root]
    candidates.extend(tuple(project_root.parents)[:4])
    configured_root = env.get("AKIHA_GPT_SOVITS_ROOT", "").strip()
    if configured_root:
        candidates.insert(0, Path(configured_root).expanduser())

    local_app_data = env.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        candidates.append(Path(local_app_data) / "Akiha" / "runtimes" / "gpt-sovits")

    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return tuple(unique)


def _probe_gpt_sovits_endpoint(base_url: str) -> bool:
    request = Request(
        f"{base_url.rstrip('/')}/openapi.json",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=0.5) as response:
            return 200 <= response.status < 300
    except (HTTPError, URLError, TimeoutError, OSError):
        return False


def _resolve_ffmpeg_bin(environment: Mapping[str, str]) -> Path | None:
    """Find FFmpeg shared libraries needed by torchcodec in the child process."""
    configured = environment.get("AKIHA_FFMPEG_BIN", "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if _is_ffmpeg_bin(candidate, tolerate_access_denied=False):
            return candidate.resolve()

    path_value = environment.get("PATH", "")
    executable = shutil.which("ffmpeg", path=path_value)
    if executable:
        return Path(executable).resolve().parent

    local_app_data = environment.get("LOCALAPPDATA", "").strip()
    if not local_app_data:
        return None
    packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
    for package in sorted(packages.glob("Gyan.FFmpeg.Shared_*")):
        for build in sorted(package.glob("ffmpeg-*"), reverse=True):
            candidate = build / "bin"
            if _is_ffmpeg_bin(candidate, tolerate_access_denied=True):
                return candidate.resolve()
    return None


def _is_ffmpeg_bin(candidate: Path, *, tolerate_access_denied: bool) -> bool:
    try:
        return (candidate / "ffmpeg.exe").is_file()
    except OSError:
        # Some per-user WinGet package ACLs deny metadata probes while still
        # allowing the child process to load DLLs from the directory.
        return tolerate_access_denied and candidate.name.casefold() == "bin"


def _start_hidden_process(
    command: Sequence[str],
    working_directory: Path,
    environment: Mapping[str, str],
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
        env=dict(environment),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
        startupinfo=startup_info,
    )
