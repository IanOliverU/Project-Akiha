"""Prepare a derived, reviewable GPT-SoVITS dataset from Akiha recordings."""

from __future__ import annotations

import json
import os
import re
import tempfile
import wave
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

from project_akiha.services.voice_audio import (
    _numpy,
    _read_pcm_wav,
    _resample,
    _trim_silence,
)

_SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


class GptSovitsDatasetError(RuntimeError):
    """Raised when a derived GPT-SoVITS dataset cannot be prepared."""


@dataclass(frozen=True, slots=True)
class GptSovitsDatasetEntry:
    """One derived audio item and its optional reviewed transcript."""

    source: str
    audio: str
    language: str
    text: str
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class GptSovitsDatasetManifest:
    """Paths and entries produced by one deterministic dataset build."""

    output_dir: Path
    manifest_path: Path
    list_path: Path
    entries: tuple[GptSovitsDatasetEntry, ...]


class GptSovitsDatasetBuilder:
    """Create derived training audio while treating source WAVs as read-only."""

    target_sample_rate = 32_000

    def __init__(
        self,
        reference_dir: Path,
        output_dir: Path,
        *,
        language: str = "ja",
        speaker: str = "akiha",
        list_name: str = "train.list",
    ) -> None:
        if not language.strip():
            raise ValueError("GPT-SoVITS dataset language cannot be empty.")
        if not speaker.strip():
            raise ValueError("GPT-SoVITS dataset speaker cannot be empty.")
        self._reference_dir = reference_dir
        self._output_dir = output_dir
        self._language = language.strip()
        self._speaker = speaker.strip()
        if not list_name.endswith(".list") or "/" in list_name or "\\" in list_name:
            raise ValueError("GPT-SoVITS list name must be a local .list filename.")
        self._list_name = list_name

    def build(
        self,
        transcripts: Mapping[str, str] | None = None,
    ) -> GptSovitsDatasetManifest:
        """Build normalized derived clips and metadata without changing sources."""
        if not self._reference_dir.is_dir():
            raise GptSovitsDatasetError(
                f"Akiha reference directory does not exist: {self._reference_dir}"
            )

        preferred = sorted(self._reference_dir.rglob("Akiha_*.wav"))
        paths = preferred or sorted(self._reference_dir.rglob("*.wav"))
        if not paths:
            raise GptSovitsDatasetError(
                "No WAV files were found in the reference directory."
            )

        transcript_map = {
            str(key).replace("\\", "/"): str(value).strip()
            for key, value in (transcripts or {}).items()
            if str(value).strip()
        }
        audio_dir = self._output_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        entries: list[GptSovitsDatasetEntry] = []
        for index, source_path in enumerate(paths, start=1):
            entry = self._build_entry(index, source_path, audio_dir, transcript_map)
            if entry is not None:
                entries.append(entry)

        if not entries:
            raise GptSovitsDatasetError(
                "No usable speech clips were found after silence filtering."
            )

        manifest_path = self._output_dir / "manifest.jsonl"
        list_path = self._output_dir / self._list_name
        self._write_manifest(manifest_path, entries)
        self._write_training_list(list_path, entries)
        return GptSovitsDatasetManifest(
            output_dir=self._output_dir,
            manifest_path=manifest_path,
            list_path=list_path,
            entries=tuple(entries),
        )

    def _build_entry(
        self,
        index: int,
        source_path: Path,
        audio_dir: Path,
        transcripts: Mapping[str, str],
    ) -> GptSovitsDatasetEntry | None:
        try:
            sample_rate, samples = _read_pcm_wav(source_path)
            trimmed, active_ratio, leading, trailing = _trim_silence(
                samples,
                sample_rate,
            )
        except (OSError, ValueError, wave.Error):
            return None

        duration = len(trimmed) / sample_rate
        if duration < 0.35 or active_ratio < 0.55 or leading > 0.75 or trailing > 0.75:
            return None

        converted = _resample(trimmed, sample_rate, self.target_sample_rate)
        converted = _normalize_audio(converted)
        safe_stem = _SAFE_NAME_PATTERN.sub("_", source_path.stem).strip("._")
        output_path = audio_dir / f"{index:04d}-{safe_stem}.wav"
        _write_wav(output_path, converted, self.target_sample_rate)
        source_key = source_path.relative_to(self._reference_dir).as_posix()
        text = transcripts.get(source_key, transcripts.get(source_path.name, ""))
        return GptSovitsDatasetEntry(
            source=source_key,
            audio=output_path.resolve().as_posix(),
            language=self._language,
            text=text,
            duration_seconds=round(len(converted) / self.target_sample_rate, 3),
        )

    @staticmethod
    def _write_manifest(
        path: Path,
        entries: list[GptSovitsDatasetEntry],
    ) -> None:
        _atomic_write_text(
            path,
            "".join(
                json.dumps(asdict(entry), ensure_ascii=False) + "\n"
                for entry in entries
            ),
        )

    def _write_training_list(
        self,
        path: Path,
        entries: list[GptSovitsDatasetEntry],
    ) -> None:
        lines = (
            f"{entry.audio}|{self._speaker}|{entry.language}|{entry.text}\n"
            for entry in entries
            if entry.text
        )
        _atomic_write_text(path, "".join(lines))


def load_transcripts(path: Path) -> dict[str, str]:
    """Load reviewed JSONL transcripts keyed by source filename or relative path."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise GptSovitsDatasetError(
            f"Could not read transcript file: {path}"
        ) from error

    transcripts: dict[str, str] = {}
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise GptSovitsDatasetError(
                f"Invalid transcript JSON on line {line_number}."
            ) from error
        if not isinstance(record, dict):
            raise GptSovitsDatasetError(
                f"Transcript line {line_number} must be a JSON object."
            )
        source = record.get("source")
        text = record.get("text")
        if isinstance(source, str) and isinstance(text, str) and text.strip():
            transcripts[source.replace("\\", "/")] = text.strip()
    return transcripts


def _normalize_audio(samples: object) -> object:
    np = _numpy()
    values = np.asarray(samples, dtype=np.float32)
    peak = float(np.max(np.abs(values))) if len(values) else 0.0
    if peak <= 1e-6:
        raise GptSovitsDatasetError("A usable clip contains no audible signal.")
    return np.clip(values * min(0.95 / peak, 1.0), -1.0, 1.0)


def _write_wav(path: Path, samples: object, sample_rate: int) -> None:
    np = _numpy()
    values = np.asarray(samples, dtype=np.float32)
    pcm = (np.clip(values, -1.0, 1.0) * 32767.0).astype("<i2", copy=False)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f"{path.stem}-",
        suffix=".wav",
        dir=path.parent,
    )
    os.close(fd)
    try:
        with wave.open(temporary_name, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            output.writeframes(pcm.tobytes())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f"{path.stem}-",
        suffix=path.suffix,
        dir=path.parent,
        text=True,
    )
    os.close(fd)
    try:
        Path(temporary_name).write_text(content, encoding="utf-8")
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
