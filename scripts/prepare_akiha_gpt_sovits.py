"""Prepare and optionally transcribe a derived GPT-SoVITS Akiha dataset."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from project_akiha.services.gpt_sovits_dataset import (
    GptSovitsDatasetBuilder,
    GptSovitsDatasetError,
    load_transcripts,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-dir", type=Path, default=Path("AKIHA VOICE"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/voice/gpt-sovits/akiha-dataset"),
    )
    parser.add_argument(
        "--transcripts",
        type=Path,
        help="Reviewed JSONL transcripts with source and text fields.",
    )
    parser.add_argument(
        "--auto-transcribe",
        action="store_true",
        help="Create a local Faster-Whisper Japanese transcript draft for review.",
    )
    parser.add_argument("--whisper-model", default="small")
    parser.add_argument("--whisper-device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()

    transcripts: dict[str, str] = {}
    if args.transcripts is not None:
        transcripts = load_transcripts(args.transcripts)

    try:
        builder = GptSovitsDatasetBuilder(
            args.reference_dir,
            args.output_dir,
            list_name="train.list" if not args.auto_transcribe else "train.auto.list",
        )
        manifest = builder.build(transcripts)
        if args.auto_transcribe:
            transcripts = _auto_transcribe(
                manifest,
                model_name=args.whisper_model,
                device=args.whisper_device,
            )
            transcript_path = args.output_dir / "transcripts.auto.jsonl"
            transcript_path.write_text(
                "".join(
                    json.dumps(
                        {"source": source, "text": text},
                        ensure_ascii=False,
                    )
                    + "\n"
                    for source, text in transcripts.items()
                ),
                encoding="utf-8",
            )
            manifest = builder.build(transcripts)
            print(f"Transcript draft: {transcript_path}")
    except (GptSovitsDatasetError, OSError, ValueError) as error:
        parser.error(str(error))

    print(f"Derived clips: {len(manifest.entries)}")
    print(f"Manifest: {manifest.manifest_path}")
    print(f"Training list: {manifest.list_path}")
    print(
        "Transcribed clips: " f"{sum(bool(entry.text) for entry in manifest.entries)}"
    )
    print(
        json.dumps(
            {
                "originals_modified": False,
                "output_dir": str(manifest.output_dir),
            },
            ensure_ascii=False,
        )
    )
    return 0


def _auto_transcribe(
    manifest: object,
    *,
    model_name: str,
    device: str,
) -> dict[str, str]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise GptSovitsDatasetError(
            "Install the voice input dependencies before using --auto-transcribe."
        ) from error

    model = WhisperModel(
        _resolve_whisper_model_path(model_name),
        device=device,
        compute_type="int8" if device == "cpu" else "float16",
        local_files_only=True,
    )
    transcripts: dict[str, str] = {}
    for index, entry in enumerate(manifest.entries, start=1):
        segments, _ = model.transcribe(
            entry.audio,
            language="ja",
            beam_size=5,
            vad_filter=False,
        )
        text = "".join(segment.text.strip() for segment in segments).strip()
        if text:
            transcripts[entry.source] = text
        print(f"Transcribed {index}/{len(manifest.entries)}: {entry.source}")
    return transcripts


def _resolve_whisper_model_path(model_name: str) -> str:
    """Prefer Project Akiha's local Faster-Whisper snapshot over network access."""
    requested = Path(model_name)
    if requested.is_dir():
        return str(requested)

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        snapshot_root = (
            Path(local_app_data)
            / "Akiha"
            / "models"
            / "faster-whisper"
            / f"models--Systran--faster-whisper-{model_name}"
            / "snapshots"
        )
        if snapshot_root.is_dir():
            snapshots = sorted(
                path for path in snapshot_root.iterdir() if path.is_dir()
            )
            if snapshots:
                return str(snapshots[-1])
    return model_name


if __name__ == "__main__":
    raise SystemExit(main())
