"""Resolve private GPT-SoVITS reference audio outside packaged artifacts."""

from __future__ import annotations

import json
import wave
from pathlib import Path

from project_akiha.services.gpt_sovits_engine_manager import (
    gpt_sovits_support_roots,
)


def resolve_gpt_sovits_prompt(
    project_root: Path,
    configured_reference_dir: str,
    configured_prompt: str,
) -> tuple[Path | None, str]:
    """Use a prepared valid reference/transcript pair when available."""
    roots = gpt_sovits_support_roots(project_root)
    for root in roots:
        manifest_path = (
            root
            / "artifacts"
            / "voice"
            / "gpt-sovits"
            / "akiha-dataset"
            / "manifest.jsonl"
        )
        if manifest_path.is_file():
            for line in manifest_path.read_text(encoding="utf-8").splitlines():
                try:
                    entry = json.loads(line)
                    audio_path = Path(str(entry.get("audio", "")))
                    text = str(entry.get("text", "")).strip()
                    if (
                        audio_path.is_file()
                        and text
                        and _is_gpt_sovits_reference(audio_path)
                    ):
                        return audio_path, configured_prompt.strip() or text
                except (OSError, TypeError, ValueError, wave.Error):
                    continue

    configured_path = Path(configured_reference_dir).expanduser()
    reference_dirs = (
        (configured_path,)
        if configured_path.is_absolute()
        else tuple(root / configured_path for root in roots)
    )
    for reference_dir in reference_dirs:
        for audio_path in sorted(reference_dir.glob("*.wav")):
            if _is_gpt_sovits_reference(audio_path):
                return audio_path, configured_prompt.strip()
    return None, configured_prompt.strip()


def _is_gpt_sovits_reference(audio_path: Path) -> bool:
    try:
        with wave.open(str(audio_path), "rb") as wav_file:
            duration = wav_file.getnframes() / wav_file.getframerate()
    except (OSError, wave.Error, ZeroDivisionError):
        return False
    return 3.0 <= duration <= 10.0
