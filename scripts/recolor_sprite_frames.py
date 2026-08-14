"""Remap sprite frames to the exact visible palette of a reference sprite."""

from __future__ import annotations

import argparse
from functools import cache
from pathlib import Path

from PIL import Image


def recolor_frames(
    *,
    source_dir: Path,
    reference_path: Path,
    output_dir: Path,
) -> tuple[Path, ...]:
    """Write palette-matched RGBA frames while preserving geometry and alpha."""
    frame_paths = tuple(sorted(source_dir.glob("*.png")))
    if not frame_paths:
        raise ValueError("The source directory contains no PNG frames.")

    reference = Image.open(reference_path).convert("RGBA")
    reference_palette = tuple(
        sorted(
            {
                (red, green, blue)
                for red, green, blue, alpha in reference.get_flattened_data()
                if alpha > 0
            }
        )
    )
    if not reference_palette:
        raise ValueError("The reference sprite contains no visible colors.")

    @cache
    def nearest_reference_color(
        color: tuple[int, int, int],
    ) -> tuple[int, int, int]:
        red, green, blue = color
        return min(
            reference_palette,
            key=lambda candidate: (
                30 * (red - candidate[0]) ** 2
                + 59 * (green - candidate[1]) ** 2
                + 11 * (blue - candidate[2]) ** 2
            ),
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for frame_path in frame_paths:
        frame = Image.open(frame_path).convert("RGBA")
        recolored = Image.new("RGBA", frame.size)
        recolored.putdata(
            [
                (
                    (*nearest_reference_color((red, green, blue)), alpha)
                    if alpha > 0
                    else (0, 0, 0, 0)
                )
                for red, green, blue, alpha in frame.get_flattened_data()
            ]
        )
        output_path = output_dir / frame_path.name
        recolored.save(output_path)
        outputs.append(output_path)
    return tuple(outputs)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    """Run reference-palette normalization for one frame directory."""
    args = _parse_args()
    outputs = recolor_frames(
        source_dir=args.source_dir,
        reference_path=args.reference,
        output_dir=args.output_dir,
    )
    for output in outputs:
        print(output)


if __name__ == "__main__":
    main()
