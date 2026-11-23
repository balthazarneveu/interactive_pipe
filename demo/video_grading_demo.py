"""
Demo: grade a video file — exposure, saturation, white balance — with a timeline.

The pipeline is written for one frame; ``Video(path)`` turns it into a video
tool: the window gets a timeline at the bottom (play / pause with space,
step with the left / right arrows, click or drag on the film strip to seek),
and every slider applies to the frame on screen.

    python demo/video_grading_demo.py                 # a generated clip
    python demo/video_grading_demo.py my_clip.mp4     # your own video (OpenCV)

The current position is available to filters as ``context["timeline"]``
(frame, time, fps): the graded output shows its timecode in its title.

Without a window: ``grading.headless(Video(path), frame=40)`` returns the
outputs at frame 40, ``grading.sweep("contact_sheet.png", Video(path),
frame=[0, 30, 60, 90])`` draws a contact sheet.
"""

import argparse
import tempfile
from pathlib import Path
from typing import List, Tuple, Union

import numpy as np

from interactive_pipe import Curve, Image, Video, context, interactive, interactive_pipeline, layout

IMAGES = Path(__file__).parent / "images"


def make_clip(path: Path, n_frames: int = 75, fps: float = 25.0, size: Tuple[int, int] = (320, 240)) -> Path:
    """A slow pan and zoom over a photo (Ken Burns effect), written as an mp4 file."""
    import cv2

    photo = (Image.load_image(IMAGES / "elephant.png") * 255).astype(np.uint8)
    height, width = photo.shape[:2]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter.fourcc(*"mp4v"), fps, size)
    for k in range(n_frames):
        progress = k / (n_frames - 1)
        zoom = 1.0 + 0.6 * progress
        crop_w, crop_h = int(width / zoom), int(height / zoom * size[1] / size[0])
        x0 = int((width - crop_w) * (0.15 + 0.7 * progress))
        y0 = int((height - crop_h) * 0.4)
        crop = photo[y0 : y0 + crop_h, x0 : x0 + crop_w]
        frame = cv2.resize(crop, size, interpolation=cv2.INTER_AREA)
        writer.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
    writer.release()
    return path


@interactive(
    exposure=(0.0, [-2.0, 2.0], "exposure (EV)"),
    saturation=(1.0, [0.0, 2.0]),
    temperature=(0.0, [-1.0, 1.0], "warm / cool"),
)
def grade(frame: np.ndarray, exposure: float = 0.0, saturation: float = 1.0, temperature: float = 0.0) -> np.ndarray:
    """Exposure in stops, saturation around the luminance, warm (+) / cool (-) balance."""
    img = frame * (2.0**exposure)
    luminance = img.mean(axis=-1, keepdims=True)
    img = luminance + saturation * (img - luminance)
    balance = np.array([1.0 + 0.2 * temperature, 1.0, 1.0 - 0.2 * temperature], dtype=np.float32)
    timeline = context["timeline"]  # written by the pipeline for Video inputs
    layout.style("graded", title=f"graded · {timeline}")
    graded: np.ndarray = np.clip(img * balance, 0.0, 1.0)
    return graded


@interactive(bins=(64, [8, 256]))
def histogram(graded: np.ndarray, bins: int = 64) -> Curve:
    """Histogram of each channel of the graded frame (a quick clipping check)."""
    edges = np.linspace(0.0, 1.0, bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2
    curves = [
        [centers, np.histogram(graded[..., channel], bins=edges)[0] / graded[..., channel].size, style, name]
        for channel, (style, name) in enumerate([("r-", "red"), ("g-", "green"), ("b-", "blue")])
    ]
    layout.style("hist", title="histogram")
    return Curve(curves, xlabel="value", ylabel="pixel fraction", grid=True)


def grading(clip: np.ndarray) -> List[List[Union[np.ndarray, Curve]]]:
    graded = grade(clip)
    hist = histogram(graded)
    return [[clip, graded], [hist]]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grade a video with a timeline")
    parser.add_argument("video", nargs="?", default=None, help="video file (default: a generated clip)")
    parser.add_argument("-b", "--backend", choices=["qt", "dpg", "gradio", "mpl"], default="qt")
    args = parser.parse_args()
    path = Path(args.video) if args.video else make_clip(Path(tempfile.gettempdir()) / "interactive_pipe_clip.mp4")
    interactive_pipeline(gui=args.backend, cache=True, name="Video grading")(grading)(Video(path))
