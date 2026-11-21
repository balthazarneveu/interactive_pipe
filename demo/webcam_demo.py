"""
Demo: live webcam processing — a cartoon effect and an edge map, tuned live.

The pipeline is written for one image; ``Webcam(0)`` feeds it the camera:
the Qt / Dear PyGui window shows a new frame about 30 times per second and
every slider applies to the live feed. Space freezes the feed (the sliders
keep working on the frozen frame), space again resumes it.

    python demo/webcam_demo.py                  # first camera
    python demo/webcam_demo.py --device 1       # another camera (or a stream URL)
    python demo/webcam_demo.py --synthetic      # no camera: a generated scene

Without a camera the demo falls back to the generated scene.

Without a window, ``cartoon.snapshot("shot.png", Webcam(0))`` grabs one frame
and saves what the window would show.
"""

import argparse
import time

import numpy as np

from interactive_pipe import Webcam, interactive, interactive_pipeline, layout


def _box_blur(img: np.ndarray, radius: int) -> np.ndarray:
    """Separable box blur (numpy only), applied twice for a smoother look."""
    if radius < 1:
        return img
    out = img
    for _ in range(2):
        for axis in (0, 1):
            pad = [(0, 0)] * out.ndim
            pad[axis] = (radius, radius)
            padded = np.pad(out, pad, mode="edge")
            cumulative = np.cumsum(padded, axis=axis, dtype=np.float32)
            zero = np.zeros_like(np.take(cumulative, [0], axis=axis))
            cumulative = np.concatenate([zero, cumulative], axis=axis)
            size = 2 * radius + 1
            n = out.shape[axis]
            out = (
                np.take(cumulative, range(size, size + n), axis=axis) - np.take(cumulative, range(n), axis=axis)
            ) / size
    return out


@interactive(levels=(6, [2, 16]), smoothing=(3, [0, 8]))
def posterize(frame, levels=6, smoothing=3):
    """Flat colour areas: blur, then quantize every channel to `levels` values."""
    smooth = _box_blur(frame, smoothing)
    return np.round(smooth * (levels - 1)) / (levels - 1)


@interactive(threshold=(0.12, [0.02, 0.4]))
def edges(frame, threshold=0.12):
    """Gradient magnitude of the luminance, thresholded to black lines."""
    luma = _box_blur(frame.mean(axis=-1), 1)
    gy, gx = np.gradient(luma)
    magnitude = np.hypot(gx, gy) * 4.0
    layout.style("edge_map", title=f"edges > {threshold:.2f}")
    return (magnitude > threshold).astype(np.float32)


@interactive()
def ink(flat, edge_map):
    """Draw the edge lines in black over the flat colours."""
    return flat * (1.0 - edge_map[..., None])


@interactive_pipeline(gui="qt", cache="graph", size=(1200, 500))
def cartoon(frame):
    flat = posterize(frame)
    edge_map = edges(frame)
    drawing = ink(flat, edge_map)
    return [frame, edge_map, drawing]


def synthetic_scene(width: int = 480, height: int = 360):
    """A function returning a new frame of a moving scene at each call (no camera needed)."""
    start = time.monotonic()
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)

    def next_frame() -> np.ndarray:
        t = time.monotonic() - start
        cx = width * (0.5 + 0.3 * np.cos(t))
        cy = height * (0.5 + 0.3 * np.sin(1.3 * t))
        disc = ((x - cx) ** 2 + (y - cy) ** 2 < (height / 5) ** 2).astype(np.float32)
        background = np.stack([x / width, y / height, 0.5 + 0.5 * np.sin(x / 40 + t) * np.cos(y / 40)], axis=-1)
        frame = background * (1 - disc[..., None]) + disc[..., None] * np.array([1.0, 0.85, 0.2], np.float32)
        return frame.astype(np.float32)

    return next_frame


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--device", default="0", help="camera index, device path or stream URL")
    parser.add_argument("--synthetic", action="store_true", help="a generated scene instead of a camera")
    parser.add_argument("--mirror", action="store_true", help="flip left / right like a video call")
    args = parser.parse_args(argv)
    source = None
    if not args.synthetic:
        device = int(args.device) if args.device.isdigit() else args.device
        try:
            source = Webcam(device, width=640, height=480, mirror=args.mirror).open()
        except (RuntimeError, ImportError) as exc:
            print(f"{exc}\n-> showing a generated scene instead")
    if source is None:
        source = Webcam(synthetic_scene(), warmup=0)
    cartoon(source)


if __name__ == "__main__":
    main()
