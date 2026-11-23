"""
Demo: check a video restoration model against the ground truth — torch tensors, two synced videos.

Two inputs share the timeline:

- ``clean``: the reference video, a numpy array at 24 fps;
- ``noisy``: what the model receives, a torch tensor ``(T, C, H, W)`` at
  12 fps (half the frames: a cheaper capture). ``Video(..., to_numpy=False)``
  hands the model the tensor slices themselves.

The timeline runs at the frame rate of the first video (24 fps); the 12 fps
video shows the frame matching the current *time*, so the comparison stays
aligned. A wipe slider compares reference and output, the error map shows
where the model fails, its title the PSNR of the frame.

Without torch installed, the "model" runs on numpy arrays (same pipeline).

    python demo/video_compare_demo.py
"""

import argparse
from pathlib import Path
from typing import Any, List

import numpy as np

from interactive_pipe import Image, Video, interactive, interactive_pipeline, layout

IMAGES = Path(__file__).parent / "images"

try:
    import torch
except ImportError:  # the demo runs on numpy arrays instead
    torch = None

#: a video frame or clip: a torch tensor (C, H, W) / (T, C, H, W), or a numpy array without torch
Frames = Any


def reference_clip(n_frames: int = 48, size: int = 160) -> np.ndarray:
    """``(T, H, W, 3)``: a photo slowly rotating and drifting (24 fps reference)."""
    import cv2

    photo = Image.load_image(IMAGES / "rabbit.png").astype(np.float32)
    photo = cv2.resize(photo, (2 * size, 2 * size), interpolation=cv2.INTER_AREA)
    frames = []
    for k in range(n_frames):
        angle = 30.0 * k / n_frames
        shift = 0.25 * size * k / n_frames
        matrix = cv2.getRotationMatrix2D((size, size), angle, 1.0)
        matrix[:, 2] += (-size / 2 + shift, -size / 2)
        frames.append(cv2.warpAffine(photo, matrix, (size, size), borderMode=cv2.BORDER_REFLECT))
    return np.stack(frames)


def noisy_capture(clean: np.ndarray, sigma: float = 0.12, seed: int = 0) -> Frames:
    """Every other frame with Gaussian noise: a ``(T/2, C, H, W)`` torch tensor (numpy without torch)."""
    rng = np.random.default_rng(seed)
    frames = clean[::2] + sigma * rng.standard_normal(clean[::2].shape).astype(np.float32)
    frames = np.clip(frames, 0.0, 1.0)
    if torch is None:
        return frames
    return torch.from_numpy(np.ascontiguousarray(frames.transpose(0, 3, 1, 2)))  # (T, C, H, W)


def to_hwc(frame: Frames) -> np.ndarray:
    """A ``(C, H, W)`` tensor or an ``(H, W, C)`` array as an ``(H, W, C)`` numpy image."""
    if torch is not None and isinstance(frame, torch.Tensor):
        return frame.detach().cpu().numpy().transpose(1, 2, 0)
    return np.asarray(frame)


@interactive(sigma=(1.2, [0.0, 4.0], "model strength"))
def denoise(noisy: Frames, sigma: float = 1.2) -> np.ndarray:
    """The "model": a Gaussian blur (a torch conv2d on tensors). Replace it with your network."""
    if sigma <= 0:
        return to_hwc(noisy)
    radius = int(3 * sigma) + 1
    taps = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma) ** 2)
    taps = (taps / taps.sum()).astype(np.float32)
    if torch is not None and isinstance(noisy, torch.Tensor):
        with torch.no_grad():
            kernel = torch.from_numpy(np.outer(taps, taps))[None, None].repeat(3, 1, 1, 1)
            batch = torch.nn.functional.pad(noisy[None], (radius,) * 4, mode="reflect")
            return to_hwc(torch.nn.functional.conv2d(batch, kernel, groups=3)[0])
    import cv2

    return cv2.sepFilter2D(np.asarray(noisy), -1, taps, taps, borderType=cv2.BORDER_REFLECT)


@interactive()
def show_input(noisy: Frames) -> np.ndarray:
    """The model input as an image (a tensor is not displayable as such)."""
    layout.style("noisy_view", title="model input (12 fps, noisy)")
    return to_hwc(noisy)


@interactive(split=(0.5, [0.0, 1.0], "wipe"))
def wipe(clean: np.ndarray, restored: np.ndarray, split: float = 0.5) -> np.ndarray:
    """Reference on the left of the wipe line, model output on the right."""
    column = int(split * clean.shape[1])
    out = np.array(restored)
    out[:, :column] = clean[:, :column]
    out[:, max(column - 1, 0) : column + 1] = (1.0, 0.8, 0.0)
    layout.style("comparison", title="reference | model output")
    return out


@interactive()
def error_map(clean: np.ndarray, restored: np.ndarray) -> np.ndarray:
    """Per-pixel absolute error, its PSNR in the title."""
    error = np.abs(restored - clean).mean(axis=-1)
    mse = float(np.mean((restored - clean) ** 2))
    psnr = 10 * np.log10(1.0 / max(mse, 1e-10))
    layout.style("error", title=f"|error| · PSNR {psnr:.1f} dB", colormap="magma", vmin=0.0, vmax=0.25, colorbar=True)
    return error


def compare(clean: np.ndarray, noisy: Frames) -> List[List[np.ndarray]]:
    restored = denoise(noisy)
    noisy_view = show_input(noisy)
    comparison = wipe(clean, restored)
    error = error_map(clean, restored)
    return [[noisy_view, comparison, error]]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare a restoration model with the reference, frame by frame")
    parser.add_argument("-b", "--backend", choices=["qt", "dpg", "gradio", "mpl"], default="qt")
    args = parser.parse_args()
    clean = reference_clip()
    interactive_pipeline(gui=args.backend, cache=True, name="Model check")(compare)(
        Video(clean, fps=24), Video(noisy_capture(clean), fps=12, to_numpy=False), frame=20
    )
