"""Tests for managed GPT-SoVITS process lifecycle."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.config import VoiceConfig
from project_akiha.services.gpt_sovits_engine_manager import (
    GptSoVitsEngineManager,
)


class GptSoVitsEngineManagerTest(unittest.TestCase):
    def test_missing_runtime_is_reported(self) -> None:
        with TemporaryDirectory() as directory:
            factory = _ProcessFactory()
            manager = GptSoVitsEngineManager(
                Path(directory),
                process_factory=factory,
                endpoint_probe=lambda _url: False,
                environment={},
            )

            status = manager.apply_config(_managed_config())

        self.assertEqual(status.state, "missing")
        self.assertTrue(status.is_error)
        self.assertEqual(factory.commands, [])

    def test_starts_and_stops_owned_runtime(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / ".gpt-sovits-src"
            (source / "GPT_SoVITS" / "configs").mkdir(parents=True)
            (source / "api_v2.py").touch()
            (source / "GPT_SoVITS" / "configs" / "tts_infer.yaml").touch()
            python = root / ".gpt-sovits-venv" / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.touch()
            ffmpeg_bin = root / "ffmpeg" / "bin"
            ffmpeg_bin.mkdir(parents=True)
            (ffmpeg_bin / "ffmpeg.exe").touch()
            factory = _ProcessFactory()
            manager = GptSoVitsEngineManager(
                root,
                process_factory=factory,
                endpoint_probe=lambda _url: False,
                environment={
                    "AKIHA_FFMPEG_BIN": str(ffmpeg_bin),
                    "PATH": "base-path",
                },
            )

            status = manager.apply_config(_managed_config())
            stopped = manager.shutdown()

        self.assertEqual(status.state, "starting")
        self.assertEqual(
            factory.commands,
            [
                (
                    str(python.resolve()),
                    str(root / "scripts" / "run_gpt_sovits_api.py"),
                    "-a",
                    "127.0.0.1",
                    "-p",
                    "9880",
                    "-c",
                    "GPT_SoVITS/configs/tts_infer.yaml",
                )
            ],
        )
        self.assertEqual(factory.working_directories, [source.resolve()])
        self.assertEqual(factory.environments[0]["PYTHONUTF8"], "1")
        self.assertTrue(
            factory.environments[0]["PATH"].startswith(str(ffmpeg_bin.resolve()))
        )
        self.assertTrue(factory.process.terminated)
        self.assertTrue(stopped)

    def test_external_runtime_is_not_stopped(self) -> None:
        factory = _ProcessFactory()
        manager = GptSoVitsEngineManager(
            Path.cwd(),
            process_factory=factory,
            endpoint_probe=lambda _url: True,
        )

        status = manager.apply_config(_managed_config())
        stopped = manager.shutdown()

        self.assertEqual(status.state, "running")
        self.assertFalse(factory.process.terminated)
        self.assertTrue(stopped)

    def test_remote_endpoint_is_rejected(self) -> None:
        factory = _ProcessFactory()
        manager = GptSoVitsEngineManager(
            Path.cwd(),
            process_factory=factory,
            endpoint_probe=lambda _url: False,
            environment={},
        )

        status = manager.apply_config(
            _managed_config(output_base_url="https://voice.example.test")
        )

        self.assertEqual(status.state, "unsupported_endpoint")
        self.assertTrue(status.is_error)
        self.assertEqual(factory.commands, [])

    def test_disabled_auto_start_does_not_launch_runtime(self) -> None:
        factory = _ProcessFactory()
        manager = GptSoVitsEngineManager(
            Path.cwd(),
            process_factory=factory,
            endpoint_probe=lambda _url: False,
            environment={},
        )

        status = manager.apply_config(_managed_config(output_engine_auto_start=False))

        self.assertEqual(status.state, "disabled")
        self.assertEqual(factory.commands, [])

    def test_wait_until_ready_accepts_owned_engine_after_loading(self) -> None:
        probes = iter((False, False, True))
        manager = GptSoVitsEngineManager(
            Path.cwd(),
            endpoint_probe=lambda _url: next(probes),
        )
        manager._process = _Process()

        ready = manager.wait_until_ready(
            "http://127.0.0.1:9880",
            timeout_seconds=0.1,
            poll_interval_seconds=0.001,
        )

        self.assertTrue(ready)

    def test_wait_until_ready_stops_when_owned_engine_exits(self) -> None:
        manager = GptSoVitsEngineManager(
            Path.cwd(),
            endpoint_probe=lambda _url: False,
        )

        ready = manager.wait_until_ready(
            "http://127.0.0.1:9880",
            timeout_seconds=0.1,
            poll_interval_seconds=0.001,
        )

        self.assertFalse(ready)


class _Process:
    def __init__(self) -> None:
        self.running = True
        self.terminated = False

    def poll(self) -> int | None:
        return None if self.running else 0

    def terminate(self) -> None:
        self.terminated = True
        self.running = False

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        self.running = False
        return 0

    def kill(self) -> None:
        self.running = False


class _ProcessFactory:
    def __init__(self) -> None:
        self.process = _Process()
        self.commands: list[tuple[str, ...]] = []
        self.working_directories: list[Path] = []
        self.environments: list[dict[str, str]] = []

    def __call__(
        self,
        command: object,
        working_directory: Path,
        environment: dict[str, str],
    ) -> _Process:
        self.commands.append(tuple(command))
        self.working_directories.append(working_directory)
        self.environments.append(environment)
        return self.process


def _managed_config(**overrides: object) -> VoiceConfig:
    values: dict[str, object] = {
        "enabled": True,
        "output_provider": "gpt-sovits",
        "output_base_url": "http://127.0.0.1:9880",
        "output_engine_auto_start": True,
    }
    values.update(overrides)
    return VoiceConfig(**values)


if __name__ == "__main__":
    unittest.main()
