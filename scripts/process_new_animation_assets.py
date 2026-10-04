"""Prepare the owner-supplied 256 px Akiha animation set for runtime use.

The checked-in source sheets remain untouched. This script extracts their grids,
removes the sheet backdrop and frame labels, normalizes every frame to RGBA, and
writes deterministic runtime assets.
"""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw

CANVAS_SIZE = 256
SOURCE_DIR_NAME = "New Sprite + Animation"


def prepare_assets(project_root: Path, base_cutout: Path) -> tuple[Path, ...]:
    """Create the complete 256 px runtime asset set."""
    animation_root = project_root / "assets" / "animations" / "akiha"
    source_root = animation_root / SOURCE_DIR_NAME
    output_root = animation_root / "seifuku-256"

    written: list[Path] = []
    base = _normalize_cutout(Image.open(base_cutout).convert("RGBA"))
    destination = output_root / "base.png"
    _save(base, destination)
    written.append(destination)

    sheet_specs = (
        (
            source_root / "Akiha’s Cozy Sleep Sprite Sheet.png",
            6,
            4,
            output_root / "sleep-start.png",
        ),
        (
            source_root / "Cozy Sleeping Loop.png",
            4,
            3,
            output_root / "sleep-loop.png",
        ),
        (
            source_root / "Akiha Wake-Up Sequence.png",
            4,
            3,
            output_root / "wake.png",
        ),
    )
    for sheet_path, columns, rows, destination in sheet_specs:
        frames = _extract_sheet(sheet_path, columns, rows)
        _save(_filmstrip(frames), destination)
        written.append(destination)

    walk_source = animation_root / "walking" / "Akiha-Walking.png"
    with Image.open(walk_source) as strip:
        strip = strip.convert("RGBA")
        frames = []
        for index in range(8):
            frame = strip.crop((index * 100, 0, (index + 1) * 100, 100))
            frames.append(
                frame.resize((CANVAS_SIZE, CANVAS_SIZE), Image.Resampling.NEAREST)
            )
        path = output_root / "walking.png"
        _save(_filmstrip(tuple(frames)), path)
        written.append(path)

    return tuple(written)


def _extract_sheet(path: Path, columns: int, rows: int) -> tuple[Image.Image, ...]:
    with Image.open(path) as source:
        source = source.convert("RGB")
        if source.width % columns or source.height % rows:
            raise ValueError(
                f"{path.name} does not divide into a {columns}x{rows} grid"
            )
        cell_width = source.width // columns
        cell_height = source.height // rows
        frames = []
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
                # The supplied sheets use rounded presentation cards with a
                # narrow border/gutter. Remove that non-animation chrome before
                # transparency extraction; the subject-safe inset is consistent
                # across every cell in a sheet.
                inset = max(2, round(min(cell.size) * 0.05))
                cell = cell.crop(
                    (inset, inset, cell.width - inset, cell.height - inset)
                )
                rgba = _remove_sheet_background(cell)
                _remove_frame_number(rgba)
                if rgba.size != (CANVAS_SIZE, CANVAS_SIZE):
                    rgba = rgba.resize(
                        (CANVAS_SIZE, CANVAS_SIZE), Image.Resampling.LANCZOS
                    )
                frames.append(rgba)
    return tuple(frames)


def _remove_sheet_background(image: Image.Image) -> Image.Image:
    """Remove only pale sheet pixels connected to the cell boundary."""
    rgb = image.convert("RGB")
    width, height = rgb.size
    pixels = rgb.load()
    removable = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def candidate(x: int, y: int) -> bool:
        red, green, blue = pixels[x, y]
        pale_blue = (
            red >= 175
            and green >= 195
            and blue >= 215
            and green >= red + 4
            and blue >= green - 2
        )
        pale_neutral = (
            min(red, green, blue) >= 220 and green >= red - 3 and blue >= green - 3
        )
        return pale_blue or pale_neutral

    def enqueue(x: int, y: int) -> None:
        offset = y * width + x
        if not removable[offset] and candidate(x, y):
            removable[offset] = 1
            queue.append((x, y))

    for x in range(width):
        enqueue(x, 0)
        enqueue(x, height - 1)
    for y in range(height):
        enqueue(0, y)
        enqueue(width - 1, y)

    while queue:
        x, y = queue.popleft()
        if x:
            enqueue(x - 1, y)
        if x + 1 < width:
            enqueue(x + 1, y)
        if y:
            enqueue(x, y - 1)
        if y + 1 < height:
            enqueue(x, y + 1)

    rgba = rgb.convert("RGBA")
    output = list(rgba.get_flattened_data())
    for offset, remove in enumerate(removable):
        if remove:
            output[offset] = (0, 0, 0, 0)
    rgba.putdata(output)
    draw = ImageDraw.Draw(rgba)
    edge = 1
    draw.rectangle((0, 0, width - 1, edge), fill=(0, 0, 0, 0))
    draw.rectangle((0, height - edge - 1, width - 1, height - 1), fill=(0, 0, 0, 0))
    draw.rectangle((0, 0, edge, height - 1), fill=(0, 0, 0, 0))
    draw.rectangle((width - edge - 1, 0, width - 1, height - 1), fill=(0, 0, 0, 0))
    return rgba


def _remove_frame_number(image: Image.Image) -> None:
    width, height = image.size
    ImageDraw.Draw(image).rectangle(
        (0, 0, round(width * 0.28), round(height * 0.16)),
        fill=(0, 0, 0, 0),
    )
    pixels = image.load()
    region_width = round(width * 0.24)
    region_height = round(height * 0.2)
    mask: set[tuple[int, int]] = set()
    for y in range(region_height):
        for x in range(region_width):
            red, green, blue, alpha = pixels[x, y]
            if alpha and blue >= 120 and blue >= red + 25 and blue >= green + 10:
                mask.add((x, y))
    expanded = set(mask)
    for x, y in mask:
        for neighbor_y in range(max(0, y - 1), min(height, y + 2)):
            for neighbor_x in range(max(0, x - 1), min(width, x + 2)):
                expanded.add((neighbor_x, neighbor_y))
    for x, y in expanded:
        pixels[x, y] = (0, 0, 0, 0)


def _normalize_cutout(image: Image.Image) -> Image.Image:
    bbox = image.getbbox()
    if bbox is None:
        raise ValueError("The generated base cutout is empty.")
    subject = image.crop(bbox)
    maximum_width = CANVAS_SIZE - 28
    maximum_height = CANVAS_SIZE - 20
    scale = min(maximum_width / subject.width, maximum_height / subject.height)
    size = (
        max(1, round(subject.width * scale)),
        max(1, round(subject.height * scale)),
    )
    subject = subject.resize(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    x = (CANVAS_SIZE - subject.width) // 2
    y = CANVAS_SIZE - 8 - subject.height
    canvas.alpha_composite(subject, (x, y))
    return canvas


def _save(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG", optimize=True)


def _filmstrip(frames: tuple[Image.Image, ...]) -> Image.Image:
    strip = Image.new("RGBA", (CANVAS_SIZE * len(frames), CANVAS_SIZE), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        strip.alpha_composite(frame, (index * CANVAS_SIZE, 0))
    return strip


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--base-cutout",
        type=Path,
        default=Path(
            "assets/animations/akiha/New Sprite + Animation/"
            "Base Sprite Transparent.png"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    written = prepare_assets(args.project_root.resolve(), args.base_cutout.resolve())
    print(f"Prepared {len(written)} runtime frames at {CANVAS_SIZE}x{CANVAS_SIZE}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
