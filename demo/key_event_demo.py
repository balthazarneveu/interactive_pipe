"""Key-bound context events demo.

Press [n] while the window is focused: the next pipeline run adds a one-shot
noise burst to the image. The GUI raises the event flag for that single run
and resets it right after; filters read it through the read-only `events`
proxy. Press [F1] to list all key bindings.
"""

import argparse

import numpy as np

from interactive_pipe import events, interactive, interactive_pipeline, layout


@interactive(brightness=(1.0, [0.0, 2.0]))
def brighten(img: np.ndarray, brightness=1.0) -> np.ndarray:
    return img * brightness


@interactive()
def noise_burst(img: np.ndarray) -> np.ndarray:
    burst = events.get("noise_burst")
    layout.style("out", title="NOISE BURST!" if burst else "press [n] for a noise burst")
    if burst:
        rng = np.random.default_rng()
        return np.clip(img + rng.normal(0.0, 0.15, img.shape), 0.0, 1.0)
    return img


def key_event_pipeline(img):
    bright = brighten(img)
    out = noise_burst(bright)
    return out


def make_gradient(size=(256, 256)) -> np.ndarray:
    h, w = size
    y, x = np.mgrid[0:h, 0:w]
    img = np.stack(
        [x / w, y / h, 0.5 + 0.5 * np.sin(2 * np.pi * (x + y) / (w + h))],
        axis=-1,
    )
    return img.astype(np.float32)


def launch(backend="qt"):
    demo = interactive_pipeline(gui=backend, cache=False, name="key event demo")(key_event_pipeline)
    # demo.pipeline is the GUI object attached by @interactive_pipeline
    demo.pipeline.bind_key_to_context("n", "noise_burst", "one-shot noise burst")
    demo(make_gradient())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Key-bound context events demo")
    parser.add_argument(
        "-b",
        "--backend",
        choices=["qt", "mpl"],  # key events need a windowed backend
        default="qt",
        help="GUI backend to use (default: qt)",
    )
    args = parser.parse_args()
    launch(backend=args.backend)
