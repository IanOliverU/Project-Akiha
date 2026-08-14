"""Tests for deterministic sprite palette normalization."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from scripts.recolor_sprite_frames import recolor_frames


class RecolorSpriteFramesTest(unittest.TestCase):
    """Verify recoloring preserves geometry while locking reference colors."""

    def test_output_uses_only_reference_colors_and_preserves_alpha(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "source"
            output_dir = root / "output"
            source_dir.mkdir()
            reference_path = root / "reference.png"
            _image(((10, 20, 30, 255), (80, 90, 100, 255))).save(reference_path)
            _image(((12, 22, 32, 255), (200, 200, 200, 0))).save(source_dir / "000.png")

            outputs = recolor_frames(
                source_dir=source_dir,
                reference_path=reference_path,
                output_dir=output_dir,
            )

            output = Image.open(outputs[0]).convert("RGBA")
            self.assertEqual(output.getpixel((0, 0)), (10, 20, 30, 255))
            self.assertEqual(output.getpixel((1, 0)), (0, 0, 0, 0))


def _image(pixels: tuple[tuple[int, int, int, int], ...]) -> Image.Image:
    image = Image.new("RGBA", (len(pixels), 1))
    image.putdata(pixels)
    return image


if __name__ == "__main__":
    unittest.main()
