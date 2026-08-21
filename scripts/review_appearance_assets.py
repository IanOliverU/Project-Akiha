"""Validate and render review artifacts for one complete Akiha appearance."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from project_akiha.core.appearance import AppearanceId, load_appearance_registry
from project_akiha.providers.animation import AssetAnimationProvider
from project_akiha.services.appearance_asset_validation import (
    AppearanceAssetReport,
    validate_appearance_manifest,
    validate_registered_appearance,
)
from project_akiha.ui.pet_renderer import PlaceholderPetRenderer, SpritePetRenderer

_REVIEW_FPS = 30
_FRAME_SIZE = 100
_CONTACT_SCALE = 4
_LABEL_HEIGHT = 28


def generate_review_artifacts(
    *,
    appearance_id: AppearanceId,
    manifest_path: Path,
    output_dir: Path,
    report: AppearanceAssetReport,
) -> tuple[Path, ...]:
    """Render production-provider frames without modifying source artwork."""
    if not report.technically_valid:
        raise ValueError("appearance must pass technical validation before preview.")
    app = QApplication.instance() or QApplication([])
    _ = app
    provider = AssetAnimationProvider.from_manifest(manifest_path)
    renderer = SpritePetRenderer(PlaceholderPetRenderer())
    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    contact_frames: list[tuple[str, QImage]] = []

    for state in sorted(provider.available_states(), key=lambda item: item.value):
        clip = provider.clip_for(state)
        state_dir = output_dir / "frames" / state.value
        state_dir.mkdir(parents=True, exist_ok=True)
        rendered: list[Path] = []
        durations: list[int] = []
        for pose_index, tick in enumerate(_pose_ticks(clip)):
            frame = provider.frame_for(state, tick)
            image = _render_frame(renderer, frame)
            path = state_dir / f"{pose_index:03d}.png"
            if not image.save(str(path), "PNG"):
                raise OSError("unable to write appearance review frame.")
            rendered.append(path)
            generated.append(path)
            contact_frames.append((f"{state.value} {pose_index + 1}", image))
            duration_ticks = (
                clip.frame_durations[pose_index]
                if clip.frame_durations
                else clip.ticks_per_frame
            )
            durations.append(max(1, round(duration_ticks * 1000 / _REVIEW_FPS)))
        gif_path = output_dir / f"{state.value}.gif"
        _write_gif(rendered, durations, gif_path)
        generated.append(gif_path)

    contact_path = output_dir / "contact-sheet.png"
    _write_contact_sheet(contact_frames, contact_path)
    generated.append(contact_path)

    report_path = output_dir / "validation-report.json"
    report_path.write_text(
        json.dumps(_serialize_report(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    generated.append(report_path)
    return tuple(generated)


def _pose_ticks(clip) -> tuple[int, ...]:  # noqa: ANN001
    if clip.frame_durations:
        ticks: list[int] = []
        elapsed = 0
        for duration in clip.frame_durations:
            ticks.append(elapsed)
            elapsed += duration
        return tuple(ticks)
    return tuple(index * clip.ticks_per_frame for index in range(len(clip.frame_paths)))


def _render_frame(renderer: SpritePetRenderer, frame) -> QImage:  # noqa: ANN001
    image = QImage(
        _FRAME_SIZE,
        _FRAME_SIZE,
        QImage.Format.Format_ARGB32,
    )
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.paint(painter, frame)
    painter.end()
    return image


def _write_gif(paths: list[Path], durations: list[int], output: Path) -> None:
    images = [Image.open(path).convert("RGBA") for path in paths]
    images[0].save(
        output,
        save_all=True,
        append_images=images[1:],
        duration=durations,
        loop=0,
        disposal=2,
        optimize=False,
    )
    for image in images:
        image.close()


def _write_contact_sheet(frames: list[tuple[str, QImage]], output: Path) -> None:
    columns = 4
    rows = (len(frames) + columns - 1) // columns
    cell_width = _FRAME_SIZE * _CONTACT_SCALE
    cell_height = cell_width + _LABEL_HEIGHT
    sheet = QImage(
        columns * cell_width,
        rows * cell_height,
        QImage.Format.Format_ARGB32,
    )
    sheet.fill(QColor("#171a22"))
    painter = QPainter(sheet)
    for index, (_label, frame) in enumerate(frames):
        column = index % columns
        row = index // columns
        x = column * cell_width
        y = row * cell_height
        enlarged = frame.scaled(
            cell_width,
            cell_width,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        painter.drawImage(x, y, enlarged)
    painter.end()
    if not sheet.save(str(output), "PNG"):
        raise OSError("unable to write appearance contact sheet.")
    with Image.open(output) as source:
        labeled = source.convert("RGBA")
    draw = ImageDraw.Draw(labeled)
    font = ImageFont.load_default()
    for index, (label, _) in enumerate(frames):
        column = index % columns
        row = index // columns
        x = column * cell_width
        y = row * cell_height + cell_width
        draw.rectangle((x, y, x + cell_width, y + _LABEL_HEIGHT), fill="#171a22")
        bounds = draw.textbbox((0, 0), label, font=font)
        text_width = bounds[2] - bounds[0]
        text_height = bounds[3] - bounds[1]
        draw.text(
            (
                x + (cell_width - text_width) // 2,
                y + (_LABEL_HEIGHT - text_height) // 2,
            ),
            label,
            fill="#d9dbea",
            font=font,
        )
    labeled.save(output, "PNG")


def _serialize_report(report: AppearanceAssetReport) -> dict[str, object]:
    return {
        "appearance_id": report.appearance_id.value,
        "manifest_name": report.manifest_path.name,
        "technically_valid": report.technically_valid,
        "approval_present": report.approval_present,
        "approval_matches": report.approval_matches,
        "activation_ready": report.activation_ready,
        "available_states": sorted(state.value for state in report.available_states),
        "unique_asset_count": report.unique_asset_count,
        "declared_frame_count": report.declared_frame_count,
        "issues": [
            {
                "code": issue.code.value,
                "state": issue.state.value if issue.state is not None else None,
                "asset_name": issue.asset_name,
            }
            for issue in report.issues
        ],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--appearance",
        choices=tuple(item.value for item in AppearanceId),
        required=True,
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("assets/animations/appearances.toml"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Validate an inactive candidate manifest without activating it.",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    appearance_id = AppearanceId(args.appearance)
    registry = load_appearance_registry(args.registry)
    if args.manifest is None:
        manifest_path = registry.manifest_path(appearance_id)
        if manifest_path is None:
            raise SystemExit(
                "The appearance is unavailable; provide --manifest to review "
                "a candidate."
            )
        report = validate_registered_appearance(registry, appearance_id)
    else:
        manifest_path = args.manifest.resolve()
        report = validate_appearance_manifest(appearance_id, manifest_path)
    output = args.output or Path("dist/appearance-review") / appearance_id.value
    generated = generate_review_artifacts(
        appearance_id=appearance_id,
        manifest_path=manifest_path,
        output_dir=output,
        report=report,
    )
    print(f"Technical validation: {'passed' if report.technically_valid else 'failed'}")
    print(f"Owner approval: {'matched' if report.approval_matches else 'not active'}")
    print(f"Generated {len(generated)} review artifact(s) under {output}.")
    return 0 if report.technically_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
