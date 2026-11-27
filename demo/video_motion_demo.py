"""
Demo: motion detection on a numpy video, with temporal filters (``window=``).

The video is a numpy array ``(T, H, W, 3)`` (a small simulation: balls
bouncing over a noisy background). ``Video(frames, window=3)`` hands each
filter the 3 frames ending at the current one, stacked as ``(3, H, W, 3)``:
enough for frame differencing and a short temporal median.

The same array is given twice: once as a plain video (the frame on screen),
once with a window. Both follow the single timeline of the window.
``frame=30`` in the call opens the window at frame 30, like any parameter.

    python demo/video_motion_demo.py
"""

import argparse
from typing import List, Tuple

import numpy as np

from interactive_pipe import Video, draw, interactive, interactive_pipeline, layout


def bouncing_balls(
    n_frames: int = 120, size: Tuple[int, int] = (180, 240), n_balls: int = 4, seed: int = 0
) -> np.ndarray:
    """``(T, H, W, 3)`` float32 frames: colored balls bouncing on a noisy gray background."""
    rng = np.random.default_rng(seed)
    height, width = size
    position = rng.uniform([20, 20], [height - 20, width - 20], size=(n_balls, 2))
    velocity = rng.uniform(-4.0, 4.0, size=(n_balls, 2))
    colors = rng.uniform(0.4, 1.0, size=(n_balls, 3))
    yy, xx = np.mgrid[:height, :width]
    frames = np.empty((n_frames, height, width, 3), dtype=np.float32)
    for k in range(n_frames):
        frame = 0.35 + 0.03 * rng.standard_normal((height, width, 1))
        frame = np.repeat(frame, 3, axis=-1)
        for ball in range(n_balls):
            inside = (yy - position[ball, 0]) ** 2 + (xx - position[ball, 1]) ** 2 < 12**2
            frame[inside] = colors[ball]
        frames[k] = np.clip(frame, 0.0, 1.0)
        position += velocity
        for axis, limit in enumerate((height, width)):
            bounce = (position[:, axis] < 12) | (position[:, axis] > limit - 12)
            velocity[bounce, axis] *= -1
    return frames


@interactive(threshold=(0.15, [0.01, 0.5]), median=(True, "temporal median"))
def motion_mask(frames: np.ndarray, threshold: float = 0.15, median: bool = True) -> np.ndarray:
    """Pixels that changed over the window: |last - first| (or - the temporal median)."""
    reference = np.median(frames, axis=0) if median else frames[0]
    change: np.ndarray = np.abs(frames[-1] - reference).max(axis=-1)
    layout.style("mask", title=f"motion (window of {len(frames)} frames)")
    return (change > threshold).astype(np.float32)


@interactive(merge=(6, [0, 20], "merge (px)"), min_area=(60, [1, 1000]))
def detect(frame: np.ndarray, mask: np.ndarray, merge: int = 6, min_area: int = 60) -> np.ndarray:
    """Boxes around the moving blobs: the mask is dilated by ``merge`` pixels (the
    leading and trailing edges of an object join), then split in connected components."""
    import cv2

    binary = (mask > 0.5).astype(np.uint8)
    if merge > 0:
        binary = np.asarray(cv2.dilate(binary, np.ones((2 * merge + 1, 2 * merge + 1), np.uint8)), dtype=np.uint8)
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(binary)
    # label 0 is the background
    boxes = [(x, y, x + w, y + h) for x, y, w, h, area in stats[1:count] if area >= min_area]
    layout.style("detections", title=f"{len(boxes)} moving object(s)")
    return draw.boxes(frame, boxes, color=(1.0, 0.2, 0.2), width=2)


def motion(frame: np.ndarray, frames: np.ndarray) -> List[np.ndarray]:
    mask = motion_mask(frames)
    detections = detect(frame, mask)
    return [frame, mask, detections]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Motion detection on a numpy video")
    parser.add_argument("-b", "--backend", choices=["qt", "dpg", "gradio", "mpl"], default="qt")
    args = parser.parse_args()
    clip = bouncing_balls()
    interactive_pipeline(gui=args.backend, cache=True, name="Motion detection")(motion)(
        Video(clip, fps=25),
        Video(clip, fps=25, window=3),
        frame=30,  # start at frame 30
    )
