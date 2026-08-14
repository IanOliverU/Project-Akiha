"""Tests for deterministic palette-safe sprite tweening."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from scripts.tween_sprite_animation import tween_loop


class TweenSpriteAnimationTest(unittest.TestCase):
    """Verify tween frames form a closed, palette-safe sequence."""

    def test_generates_each_transition_without_duplicate_loop_endpoint(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            reference_path = root / "reference.png"
            first_path = root / "first.png"
            second_path = root / "second.png"
            output_dir = root / "output"
            _image(((10, 20, 30, 255), (80, 90, 100, 255))).save(reference_path)
            _image(((10, 20, 30, 255), (0, 0, 0, 0))).save(first_path)
            _image(((80, 90, 100, 255), (80, 90, 100, 255))).save(second_path)

            outputs = tween_loop(
                keyframe_paths=(first_path, second_path),
                reference_path=reference_path,
                output_dir=output_dir,
                frames_per_transition=3,
            )

            self.assertEqual(len(outputs), 6)
            self.assertEqual(outputs[0].name, "000.png")
            self.assertEqual(outputs[-1].name, "005.png")
            first = Image.open(outputs[0]).convert("RGBA")
            last = Image.open(outputs[-1]).convert("RGBA")
            self.assertNotEqual(
                tuple(first.get_flattened_data()), tuple(last.get_flattened_data())
            )
            allowed = {(10, 20, 30), (80, 90, 100)}
            for output in outputs:
                image = Image.open(output).convert("RGBA")
                self.assertTrue(
                    all(
                        (red, green, blue) in allowed
                        for red, green, blue, alpha in image.get_flattened_data()
                        if alpha > 0
                    )
                )

    def test_rejects_mismatched_keyframe_dimensions(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            reference_path = root / "reference.png"
            first_path = root / "first.png"
            second_path = root / "second.png"
            _image(((10, 20, 30, 255),)).save(reference_path)
            _image(((10, 20, 30, 255),)).save(first_path)
            Image.new("RGBA", (2, 2), (10, 20, 30, 255)).save(second_path)

            with self.assertRaisesRegex(ValueError, "same dimensions"):
                tween_loop(
                    keyframe_paths=(first_path, second_path),
                    reference_path=reference_path,
                    output_dir=root / "output",
                    frames_per_transition=2,
                )


def _image(pixels: tuple[tuple[int, int, int, int], ...]) -> Image.Image:
    image = Image.new("RGBA", (len(pixels), 1))
    image.putdata(pixels)
    return image


if __name__ == "__main__":
    unittest.main()
