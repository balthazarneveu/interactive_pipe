"""
Demo: blend two videos on one timeline: cross-fade, a dissolve over time, difference, wipe.

Two clips of different lengths and frame rates are given as two ``Video``
inputs. They share the timeline (one lane each on the film strip, under one
playhead); each filter receives the frame of both clips at the current time.

- ``elephant``: 3 s at 25 fps, a slow pan;
- ``rabbit``: 2 s at 12 fps, a zoom; past its end it holds its last frame
  (its lane on the strip ends there).

``dissolve`` ignores the ``mix`` slider and fades from one clip to the other
as the timeline plays (``context["timeline"].progress``).

    python demo/video_blend_demo.py
"""

import argparse
from pathlib import Path
from typing import List

import numpy as np

from interactive_pipe import Image, Video, context, interactive, interactive_pipeline, layout

IMAGES = Path(__file__).parent / "images"
SIZE = 160


def photo(name: str) -> np.ndarray:
    import cv2

    image = Image.load_image(IMAGES / f"{name}.png").astype(np.float32)
    return cv2.resize(image, (2 * SIZE, 2 * SIZE), interpolation=cv2.INTER_AREA)


def pan_clip(n_frames: int = 75) -> np.ndarray:
    """``(T, SIZE, SIZE, 3)``: a window sliding across the photo."""
    image = photo("elephant")
    return np.stack([image[SIZE // 2 : SIZE // 2 + SIZE, k * SIZE // n_frames :][:, :SIZE] for k in range(n_frames)])


def zoom_clip(n_frames: int = 24) -> np.ndarray:
    """``(T, SIZE, SIZE, 3)``: a zoom into the photo."""
    import cv2

    image = photo("rabbit")
    frames = []
    for k in range(n_frames):
        matrix = cv2.getRotationMatrix2D((SIZE, SIZE), 0.0, 1.0 + k / n_frames)
        matrix[:, 2] -= SIZE / 2
        frames.append(cv2.warpAffine(image, matrix, (SIZE, SIZE), borderMode=cv2.BORDER_REFLECT))
    return np.stack(frames)


@interactive(
    mode=(["cross-fade", "dissolve", "difference", "wipe"], "blend"),
    mix=(0.5, [0.0, 1.0]),
)
def blend(a: np.ndarray, b: np.ndarray, mode: str = "cross-fade", mix: float = 0.5) -> np.ndarray:
    """Combine the two frames; ``mix`` weighs ``b`` (or places the wipe line)."""
    if mode == "dissolve":
        mix = context["timeline"].progress  # from a to b over the whole timeline
    if mode == "difference":
        out = np.clip(2.0 * np.abs(a - b), 0.0, 1.0)
    elif mode == "wipe":
        column = int(mix * a.shape[1])
        out = np.array(b)
        out[:, :column] = a[:, :column]
        out[:, max(column - 1, 0) : column + 1] = (1.0, 0.8, 0.0)
    else:
        out = (1.0 - mix) * a + mix * b
    layout.style("blended", title=f"dissolve: {mix:.0%} rabbit" if mode == "dissolve" else mode)
    return out


def blend_videos(elephant: np.ndarray, rabbit: np.ndarray) -> List[np.ndarray]:
    blended = blend(elephant, rabbit)
    return [elephant, blended, rabbit]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Blend two videos sharing one timeline")
    parser.add_argument("-b", "--backend", choices=["qt", "dpg", "gradio", "mpl"], default="qt")
    args = parser.parse_args()
    interactive_pipeline(gui=args.backend, cache=True, name="Blend two videos")(blend_videos)(
        Video(pan_clip(), fps=25), Video(zoom_clip(), fps=12), frame=30
    )
