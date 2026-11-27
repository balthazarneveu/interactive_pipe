"""
Demo: mouse input with PointControl and RegionControl.

- click on the image: the row under the click is plotted as a profile
  (one curve per channel);
- shift-drag on the image: the region is cropped and shown enlarged.

The window draws the marker and the rectangle over the image (Qt, Dear PyGui,
matplotlib; a click only on Gradio). Where gestures are not available
(notebook, or a backend that does not implement them) the point and the
region are sliders: ``seed x``, ``seed y``, ``roi x0`` ... ``roi y1``.

Coordinates are fractions of the image size in [0, 1]; ``to_pixels`` gives the
pixel (point) or the slice bounds (region) in each filter.
"""

import argparse
from pathlib import Path
from typing import List, Tuple, Union

import numpy as np

from interactive_pipe import (
    Curve,
    PointControl,
    RegionControl,
    interactive,
    interactive_pipeline,
    layout,
    to_pixels,
)

IMAGE_PATH = Path(__file__).parent / "images" / "elephant.png"


@interactive()
def load_image() -> np.ndarray:
    """The elephant sample image (a synthetic pattern when Pillow is missing)."""
    try:
        from PIL import Image

        return np.asarray(Image.open(IMAGE_PATH).convert("RGB"), dtype=np.float32) / 255.0
    except (ImportError, OSError):
        y, x = np.mgrid[0:256, 0:384].astype(np.float32)
        return np.stack([x / 383.0, y / 255.0, 0.5 + 0.5 * np.sin(x / 9.0) * np.cos(y / 13.0)], axis=-1)


@interactive(seed=PointControl((0.65, 0.5), on="img", name="seed"))
def row_profile(img: np.ndarray, seed: Tuple[float, float] = (0.65, 0.5)) -> Curve:
    """Pixel values along the row under the clicked point, one curve per channel."""
    col, row = to_pixels(seed, img)
    columns = np.arange(img.shape[1])
    curves = [
        [columns, img[row, :, channel], style, name]
        for channel, (style, name) in enumerate([("r-", "red"), ("g-", "green"), ("b-", "blue")])
    ]
    curves.append([[col, col], [0.0, 1.0], "k--", f"x={col}"])
    layout.style("profile", title=f"Row {row} profile")
    return Curve(curves, xlabel="column [pixels]", ylabel="value", ylim=(0.0, 1.0), grid=True)


@interactive(roi=RegionControl((0.3, 0.25, 0.6, 0.55), on="img", name="roi"), zoom=(4, [1, 8]))
def zoom_region(
    img: np.ndarray, roi: Tuple[float, float, float, float] = (0.3, 0.25, 0.6, 0.55), zoom: int = 4
) -> np.ndarray:
    """The dragged region, enlarged `zoom` times (nearest neighbour: pixels stay visible)."""
    x0, y0, x1, y1 = to_pixels(roi, img)
    crop = img[y0:y1, x0:x1]
    layout.style("crop", title=f"Region x {x0}:{x1}, y {y0}:{y1} (x{zoom})")
    return np.repeat(np.repeat(crop, zoom, axis=0), zoom, axis=1)


def pointer_pipeline() -> List[List[Union[np.ndarray, Curve]]]:
    img = load_image()
    profile = row_profile(img)
    crop = zoom_region(img)
    return [[img, crop], [profile]]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Click a point, drag a region (shift + drag)")
    parser.add_argument(
        "-b",
        "--backend",
        type=str,
        choices=["qt", "dpg", "gradio", "mpl", "nb"],
        default="qt",
        help="Backend to use (default: qt)",
    )
    args = parser.parse_args()
    interactive_pipeline(gui=args.backend, cache=True, name="Pointer demo")(pointer_pipeline)()
