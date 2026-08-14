"""Normalize a reference-guided sprite grid for review."""

from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw

_ALPHA_THRESHOLD = 16
_SAFE_MARGIN = 2


def process_sprite_grid(
    *,
    input_path: Path,
    reference_path: Path,
    output_dir: Path,
    rows: int,
    columns: int,
    canvas_size: int,
    frame_duration_ms: int,
) -> dict[str, object]:
    """Export aligned frames and return their QC metadata."""
    if rows <= 0 or columns <= 0 or canvas_size <= 0:
        raise ValueError("Rows, columns, and canvas size must be positive.")

    source = Image.open(input_path).convert("RGBA")
    reference = Image.open(reference_path).convert("RGBA")
    if source.width % columns or source.height % rows:
        raise ValueError("The source dimensions must divide evenly into the grid.")

    reference_bbox = _alpha_bbox(reference)
    cells = _extract_subject_cells(source, rows=rows, columns=columns)
    source_bboxes = [_alpha_bbox(cell) for cell in cells]
    maximum_width = max(_bbox_width(bbox) for bbox in source_bboxes)
    maximum_height = max(_bbox_height(bbox) for bbox in source_bboxes)
    reference_bottom = min(reference_bbox[3], canvas_size - _SAFE_MARGIN)
    available_width = min(
        _bbox_width(reference_bbox),
        canvas_size - 2 * _SAFE_MARGIN,
    )
    available_height = reference_bottom - _SAFE_MARGIN
    shared_scale = min(
        available_width / maximum_width,
        available_height / maximum_height,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    frames = [
        _normalize_frame(
            cell,
            source_bbox=bbox,
            reference_bbox=reference_bbox,
            canvas_size=canvas_size,
            shared_scale=shared_scale,
        )
        for cell, bbox in zip(cells, source_bboxes, strict=True)
    ]

    frame_records = []
    for index, (frame, source_bbox) in enumerate(
        zip(frames, source_bboxes, strict=True)
    ):
        frame_path = output_dir / f"frame-{index:03d}.png"
        frame.save(frame_path)
        output_bbox = _alpha_bbox(frame)
        frame_records.append(
            {
                "index": index,
                "path": frame_path.name,
                "source_bbox": list(source_bbox),
                "output_bbox": list(output_bbox),
                "output_edge_touch": _touches_edge(output_bbox, frame.size),
            }
        )

    filmstrip = Image.new("RGBA", (canvas_size * len(frames), canvas_size))
    for index, frame in enumerate(frames):
        filmstrip.alpha_composite(frame, (index * canvas_size, 0))
    filmstrip.save(output_dir / "filmstrip.png")

    frames[0].save(
        output_dir / "animation.gif",
        save_all=True,
        append_images=frames[1:],
        duration=frame_duration_ms,
        loop=0,
        disposal=2,
    )
    _make_review_contact_sheet(frames).save(output_dir / "review-contact-sheet.png")

    metadata: dict[str, object] = {
        "status": "prototype_owner_review_required",
        "source": input_path.as_posix(),
        "reference": reference_path.as_posix(),
        "source_dimensions": [source.width, source.height],
        "source_grid": {"rows": rows, "columns": columns},
        "runtime_canvas": [canvas_size, canvas_size],
        "frame_count": len(frames),
        "frame_duration_ms": frame_duration_ms,
        "alignment": "bottom_center_reference_feet",
        "scale_strategy": "shared_preserve",
        "safe_margin": _SAFE_MARGIN,
        "shared_scale": round(shared_scale, 6),
        "reference_bbox": list(reference_bbox),
        "frames": frame_records,
        "checks": {
            "rgba": all(frame.mode == "RGBA" for frame in frames),
            "uniform_dimensions": all(
                frame.size == (canvas_size, canvas_size) for frame in frames
            ),
            "transparent_corners": all(
                _corners_are_transparent(frame) for frame in frames
            ),
            "no_output_edge_touch": not any(
                record["output_edge_touch"] for record in frame_records
            ),
            "owner_identity_and_motion_review": False,
        },
    }
    (output_dir / "pipeline-meta.json").write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )
    return metadata


def _extract_subject_cells(
    source: Image.Image,
    *,
    rows: int,
    columns: int,
) -> list[Image.Image]:
    cell_width = source.width // columns
    cell_height = source.height // rows
    cells = []
    for row in range(rows):
        for column in range(columns):
            cell = source.crop(
                (
                    column * cell_width,
                    row * cell_height,
                    (column + 1) * cell_width,
                    (row + 1) * cell_height,
                )
            )
            cells.append(_keep_center_subject(cell))
    return cells


def _keep_center_subject(image: Image.Image) -> Image.Image:
    alpha = image.getchannel("A")
    width, height = image.size
    opaque = alpha.load()
    candidates = (
        (x, y)
        for y in range(height)
        for x in range(width)
        if opaque[x, y] >= _ALPHA_THRESHOLD
    )
    try:
        seed = min(
            candidates,
            key=lambda point: (point[0] - width / 2) ** 2
            + (point[1] - height / 2) ** 2,
        )
    except ValueError as error:
        raise ValueError("A generated sprite cell is empty.") from error

    selected = bytearray(width * height)
    selected[seed[1] * width + seed[0]] = 1
    queue = deque([seed])
    while queue:
        x, y = queue.popleft()
        for neighbor_y in range(max(0, y - 1), min(height, y + 2)):
            for neighbor_x in range(max(0, x - 1), min(width, x + 2)):
                offset = neighbor_y * width + neighbor_x
                if (
                    selected[offset]
                    or opaque[neighbor_x, neighbor_y] < _ALPHA_THRESHOLD
                ):
                    continue
                selected[offset] = 1
                queue.append((neighbor_x, neighbor_y))

    cleaned = image.copy()
    cleaned_alpha = cleaned.getchannel("A")
    alpha_pixels = cleaned_alpha.load()
    for y in range(height):
        for x in range(width):
            if not selected[y * width + x]:
                alpha_pixels[x, y] = 0
    cleaned.putalpha(cleaned_alpha)
    return cleaned


def _normalize_frame(
    image: Image.Image,
    *,
    source_bbox: tuple[int, int, int, int],
    reference_bbox: tuple[int, int, int, int],
    canvas_size: int,
    shared_scale: float,
) -> Image.Image:
    subject = image.crop(source_bbox)
    output_width = max(1, round(subject.width * shared_scale))
    output_height = max(1, round(subject.height * shared_scale))
    subject = subject.resize(
        (output_width, output_height),
        Image.Resampling.NEAREST,
    )

    reference_center_x = (reference_bbox[0] + reference_bbox[2]) / 2
    reference_bottom = min(reference_bbox[3], canvas_size - _SAFE_MARGIN)
    x = round(reference_center_x - output_width / 2)
    y = round(reference_bottom - output_height)
    canvas = Image.new("RGBA", (canvas_size, canvas_size))
    canvas.alpha_composite(subject, (x, y))
    return canvas


def _make_review_contact_sheet(frames: list[Image.Image]) -> Image.Image:
    cell_size = 300
    columns = 2
    rows = (len(frames) + columns - 1) // columns
    sheet = Image.new("RGBA", (columns * cell_size, rows * cell_size))
    draw = ImageDraw.Draw(sheet)
    checker_size = 15
    for y in range(0, sheet.height, checker_size):
        for x in range(0, sheet.width, checker_size):
            value = 42 if (x // checker_size + y // checker_size) % 2 else 55
            draw.rectangle(
                (x, y, x + checker_size - 1, y + checker_size - 1),
                fill=(value, value, value, 255),
            )
    for index, frame in enumerate(frames):
        enlarged = frame.resize((cell_size, cell_size), Image.Resampling.NEAREST)
        sheet.alpha_composite(
            enlarged,
            ((index % columns) * cell_size, (index // columns) * cell_size),
        )
    return sheet


def _alpha_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("A sprite image has no visible pixels.")
    return bbox


def _bbox_width(bbox: tuple[int, int, int, int]) -> int:
    return bbox[2] - bbox[0]


def _bbox_height(bbox: tuple[int, int, int, int]) -> int:
    return bbox[3] - bbox[1]


def _touches_edge(
    bbox: tuple[int, int, int, int],
    image_size: tuple[int, int],
) -> bool:
    return (
        bbox[0] == 0
        or bbox[1] == 0
        or bbox[2] == image_size[0]
        or bbox[3] == image_size[1]
    )


def _corners_are_transparent(image: Image.Image) -> bool:
    alpha = image.getchannel("A")
    return all(
        alpha.getpixel(point) == 0
        for point in (
            (0, 0),
            (image.width - 1, 0),
            (0, image.height - 1),
            (image.width - 1, image.height - 1),
        )
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=2)
    parser.add_argument("--columns", type=int, default=2)
    parser.add_argument("--canvas-size", type=int, default=100)
    parser.add_argument("--frame-duration-ms", type=int, default=180)
    return parser.parse_args()


def main() -> None:
    """Run the command-line prototype processor."""
    args = _parse_args()
    metadata = process_sprite_grid(
        input_path=args.input,
        reference_path=args.reference,
        output_dir=args.output_dir,
        rows=args.rows,
        columns=args.columns,
        canvas_size=args.canvas_size,
        frame_duration_ms=args.frame_duration_ms,
    )
    print(json.dumps(metadata["checks"], indent=2))


if __name__ == "__main__":
    main()
