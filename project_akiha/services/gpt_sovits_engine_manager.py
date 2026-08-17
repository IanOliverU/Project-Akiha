"""Lifecycle management for the local GPT-SoVITS API process."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
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


ProcessFactory = Callable[
    [Sequence[str], Path, Mapping[str, str]],
    ManagedEngineProcess,
]
EndpointProbe = Callable[[str], bool]


class GptSoVitsEngineManager:
    """Start and stop only the GPT-SoVITS process owned by Akiha."""

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
        self._endpoint_probe = endpoint_probe or _probe_gpt_sovits_endpoint
        self._environment = environment if environment is not None else os.environ
        self._process: ManagedEngineProcess | None = None
        self._launch_signature: tuple[Path, Path, str, int] | None = None
        self._stop_on_exit = True

    @property
    def owns_running_process(self) -> bool:
        """Return whether Akiha owns a running GPT-SoVITS process."""
        return self._process is not None and self._process.poll() is None

    def apply_config(self, config: VoiceConfig) -> GptSoVitsEngineStatus:
        """Start GPT-SoVITS for the active local Akiha voice configuration."""
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

        runtime = self._resolve_runtime()
        if runtime is None:
            self.stop()
            return GptSoVitsEngineStatus(
                "missing",
                "Install the isolated GPT-SoVITS runtime before starting voice output.",
                True,
            )

        python_executable, source_dir, config_path = runtime
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
            str(self._project_root / "scripts" / "run_gpt_sovits_api.py"),
            "-a",
            host,
            "-p",
            str(port),
            "-c",
            config_path.relative_to(source_dir).as_posix(),
        )
        environment = self._process_environment()
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

    def stop(self, timeout_seconds: float = 5.0) -> bool:
        """Stop the owned process without touching an external API process."""
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
        if not self._stop_on_exit:
            self._process = None
            self._launch_signature = None
            return True
        return self.stop()

    def _resolve_runtime(self) -> tuple[Path, Path, Path] | None:
        source_candidates = []
        configured_source = self._environment.get("AKIHA_GPT_SOVITS_SOURCE", "").strip()
        if configured_source:
            source_candidates.append(Path(configured_source).expanduser())
        source_candidates.append(self._project_root / ".gpt-sovits-src")

        python_candidates = []
        configured_python = self._environment.get("AKIHA_GPT_SOVITS_PYTHON", "").strip()
        if configured_python:
            python_candidates.append(Path(configured_python).expanduser())
        python_candidates.extend(
            (
                self._project_root / ".gpt-sovits-venv" / "Scripts" / "python.exe",
                self._project_root / ".gpt-sovits-venv" / "bin" / "python",
            )
        )
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
                    return python_executable, source, config_path
        return None

    def _process_environment(self) -> dict[str, str]:
        environment = dict(self._environment)
        nltk_data = self._project_root / ".gpt-sovits-venv" / "nltk_data"
        if nltk_data.is_dir():
            environment["NLTK_DATA"] = str(nltk_data)
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
