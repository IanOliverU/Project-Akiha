"""Tests for managed standalone VOICEVOX Engine lifecycle."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.config import VoiceConfig
from project_akiha.services.voicevox_engine_manager import (
    VoiceVoxEngineManager,
)


class VoiceVoxEngineManagerTest(unittest.TestCase):
    """Verify safe launch ownership and shutdown behavior."""

    def test_disabled_management_does_not_start_process(self) -> None:
        factory = _ProcessFactory()
        manager = VoiceVoxEngineManager(
            Path.cwd(),
            process_factory=factory,
            endpoint_probe=lambda _url: False,
        )

        status = manager.apply_config(VoiceConfig(enabled=True))

        self.assertEqual(status.state, "disabled")
        self.assertEqual(factory.commands, [])

    def test_running_external_engine_is_not_started_or_stopped(self) -> None:
        factory = _ProcessFactory()
        manager = VoiceVoxEngineManager(
            Path.cwd(),
            process_factory=factory,
            endpoint_probe=lambda _url: True,
        )

        status = manager.apply_config(_managed_config())
        stopped = manager.shutdown()

        self.assertEqual(status.state, "external")
        self.assertEqual(factory.commands, [])
        self.assertTrue(stopped)

    def test_missing_executable_is_reported(self) -> None:
        manager = VoiceVoxEngineManager(
            Path.cwd(),
            process_factory=_ProcessFactory(),
            endpoint_probe=lambda _url: False,
            environment={},
        )

        status = manager.apply_config(
            _managed_config(output_engine_path="missing-engine.exe")
        )

        self.assertEqual(status.state, "missing")
        self.assertTrue(status.is_error)

    def test_starts_local_engine_with_endpoint_and_stops_owned_process(self) -> None:
        with TemporaryDirectory() as directory:
            executable = Path(directory) / "run.exe"
            executable.touch()
            factory = _ProcessFactory()
            manager = VoiceVoxEngineManager(
                Path(directory),
                process_factory=factory,
                endpoint_probe=lambda _url: False,
            )

            status = manager.apply_config(
                _managed_config(output_engine_path=str(executable))
            )
            stopped = manager.shutdown()

        self.assertEqual(status.state, "starting")
        self.assertEqual(
            factory.commands,
            [
                (
                    str(executable.resolve()),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "50021",
                )
            ],
        )
        self.assertEqual(factory.working_directories, [executable.parent.resolve()])
        self.assertTrue(factory.process.terminated)
        self.assertTrue(stopped)

    def test_stop_on_exit_false_leaves_owned_process_running(self) -> None:
        with TemporaryDirectory() as directory:
            executable = Path(directory) / "run.exe"
            executable.touch()
            factory = _ProcessFactory()
            manager = VoiceVoxEngineManager(
                Path(directory),
                process_factory=factory,
                endpoint_probe=lambda _url: False,
            )
            manager.apply_config(
                _managed_config(
                    output_engine_path=str(executable),
                    output_engine_stop_on_exit=False,
                )
            )

            stopped = manager.shutdown()

        self.assertTrue(stopped)
        self.assertFalse(factory.process.terminated)

    def test_remote_endpoint_is_rejected_before_launch(self) -> None:
        factory = _ProcessFactory()
        manager = VoiceVoxEngineManager(
            Path.cwd(),
            process_factory=factory,
            endpoint_probe=lambda _url: False,
        )

        status = manager.apply_config(
            _managed_config(output_base_url="https://voice.example.test")
        )

        self.assertEqual(status.state, "unsupported_endpoint")
        self.assertTrue(status.is_error)
        self.assertEqual(factory.commands, [])

    def test_environment_path_is_auto_discovered(self) -> None:
        with TemporaryDirectory() as directory:
            executable = Path(directory) / "run.exe"
            executable.touch()
            factory = _ProcessFactory()
            manager = VoiceVoxEngineManager(
                Path(directory),
                process_factory=factory,
                endpoint_probe=lambda _url: False,
                environment={"VOICEVOX_ENGINE_PATH": str(executable)},
            )

            status = manager.apply_config(_managed_config())
            manager.stop()

        self.assertEqual(status.state, "starting")
        self.assertEqual(factory.commands[0][0], str(executable.resolve()))

    def test_standard_voicevox_install_is_auto_discovered(self) -> None:
        with TemporaryDirectory() as directory:
            executable = (
                Path(directory) / "Programs" / "VOICEVOX" / "vv-engine" / "run.exe"
            )
            executable.parent.mkdir(parents=True)
            executable.touch()
            factory = _ProcessFactory()
            manager = VoiceVoxEngineManager(
                Path(directory),
                process_factory=factory,
                endpoint_probe=lambda _url: False,
                environment={"LOCALAPPDATA": directory},
            )

            status = manager.apply_config(_managed_config())
            manager.stop()

        self.assertEqual(status.state, "starting")
        self.assertEqual(factory.commands[0][0], str(executable.resolve()))

    def test_timeout_forces_owned_process_to_stop(self) -> None:
        with TemporaryDirectory() as directory:
            executable = Path(directory) / "run.exe"
            executable.touch()
            process = _Process(timeout_on_terminate=True)
            factory = _ProcessFactory(process)
            manager = VoiceVoxEngineManager(
                Path(directory),
                process_factory=factory,
                endpoint_probe=lambda _url: False,
            )
            manager.apply_config(_managed_config(output_engine_path=str(executable)))

            stopped = manager.stop(timeout_seconds=0.01)

        self.assertTrue(stopped)
        self.assertTrue(process.killed)


class _Process:
    def __init__(self, *, timeout_on_terminate: bool = False) -> None:
        self.running = True
        self.terminated = False
        self.killed = False
        self.timeout_on_terminate = timeout_on_terminate

    def poll(self) -> int | None:
        return None if self.running else 0

    def terminate(self) -> None:
        self.terminated = True
        if not self.timeout_on_terminate:
            self.running = False

    def wait(self, timeout: float | None = None) -> int:
        if self.running and self.timeout_on_terminate and not self.killed:
            raise subprocess.TimeoutExpired("run.exe", timeout)
        self.running = False
        return 0

    def kill(self) -> None:
        self.killed = True
        self.running = False


class _ProcessFactory:
    def __init__(self, process: _Process | None = None) -> None:
        self.process = process or _Process()
        self.commands: list[tuple[str, ...]] = []
        self.working_directories: list[Path] = []

    def __call__(
        self,
        command: object,
        working_directory: Path,
    ) -> _Process:
        self.commands.append(tuple(command))
        self.working_directories.append(working_directory)
        return self.process


def _managed_config(**overrides: object) -> VoiceConfig:
    values: dict[str, object] = {
        "enabled": True,
        "output_engine_auto_start": True,
    }
    values.update(overrides)
    return VoiceConfig(**values)


if __name__ == "__main__":
    unittest.main()
