"""Create palette-safe in-between frames for a looping sprite animation."""

from __future__ import annotations

import argparse
from functools import cache
from pathlib import Path

from PIL import Image


def tween_loop(
    *,
    keyframe_paths: tuple[Path, ...],
    reference_path: Path,
    output_dir: Path,
    frames_per_transition: int,
) -> tuple[Path, ...]:
    """Tween a closed keyframe loop while preserving alpha and reference colors."""
    if len(keyframe_paths) < 2:
        raise ValueError("At least two keyframes are required.")
    if frames_per_transition <= 0:
        raise ValueError("frames_per_transition must be greater than zero.")

    keyframes = tuple(Image.open(path).convert("RGBA") for path in keyframe_paths)
    frame_size = keyframes[0].size
    if any(frame.size != frame_size for frame in keyframes):
        raise ValueError("All keyframes must have the same dimensions.")

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
    outputs: list[Path] = []
    output_index = 0
    for keyframe_index, start in enumerate(keyframes):
        end = keyframes[(keyframe_index + 1) % len(keyframes)]
        start_pixels = tuple(start.get_flattened_data())
        end_pixels = tuple(end.get_flattened_data())
        for step in range(frames_per_transition):
            numerator = step
            denominator = frames_per_transition
            pixels = []
            for start_pixel, end_pixel in zip(
                start_pixels,
                end_pixels,
                strict=True,
            ):
                blended = tuple(
                    round(
                        (
                            start_channel * (denominator - numerator)
                            + end_channel * numerator
                        )
                        / denominator
                    )
                    for start_channel, end_channel in zip(
                        start_pixel,
                        end_pixel,
                        strict=True,
                    )
                )
                red, green, blue, alpha = blended
            pixels.append(
                (*nearest_reference_color((red, green, blue)), alpha)
                if alpha > 0
                else (0, 0, 0, 0)
            )

            output = Image.new("RGBA", frame_size)
            output.putdata(pixels)
            output_path = output_dir / f"{output_index:03}.png"
            output.save(output_path)
            outputs.append(output_path)
            output_index += 1

    return tuple(outputs)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keyframe", type=Path, action="append", required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--frames-per-transition", type=int, default=8)
    return parser.parse_args()


def main() -> None:
    """Generate one closed sprite animation loop."""
    args = _parse_args()
    outputs = tween_loop(
        keyframe_paths=tuple(args.keyframe),
        reference_path=args.reference,
        output_dir=args.output_dir,
        frames_per_transition=args.frames_per_transition,
    )
    for output in outputs:
        print(output)


if __name__ == "__main__":
    main()
