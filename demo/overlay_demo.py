"""
Demo: drawing detections on an image with interactive_pipe.draw.

Synthetic blobs are thresholded; each connected region is a detection.
- "detections": the image with a box, a centroid and a label per region,
  the count in the title;
- "regions": the label mask blended over the image (one colour per region).

Move the threshold slider: regions split, merge and disappear.
No OpenCV or scipy needed: draw only uses numpy and Pillow.
"""

import argparse
from typing import List, Tuple

import numpy as np

from interactive_pipe import draw, interactive, interactive_pipeline, layout

SIZE = (240, 320)  # (height, width)


@interactive(blobs=(12, [1, 30]), noise=(0.05, [0.0, 0.3]))
def synthetic_blobs(blobs: int = 12, noise: float = 0.05) -> np.ndarray:
    """Gaussian blobs of random sizes and brightness on a noisy background."""
    rng = np.random.default_rng(0)
    height, width = SIZE
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)
    img = np.zeros(SIZE, dtype=np.float32)
    for _ in range(blobs):
        cx, cy = rng.uniform(15, width - 15), rng.uniform(15, height - 15)
        sigma = rng.uniform(4.0, 14.0)
        img += rng.uniform(0.4, 1.0) * np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2.0 * sigma**2))
    img += noise * np.random.default_rng(1).standard_normal(SIZE).astype(np.float32)
    gray = np.clip(img, 0.0, 1.0)
    return np.stack([gray * 0.9, gray * 0.95, gray], axis=-1)  # slightly tinted RGB


def connected_regions(mask: np.ndarray) -> np.ndarray:
    """4-connected labels (1..N, 0 = background) by label propagation, numpy only."""
    labels = np.where(mask, np.arange(1, mask.size + 1, dtype=np.int64).reshape(mask.shape), 0)
    big = np.iinfo(np.int64).max
    while True:
        padded = np.pad(np.where(mask, labels, big), 1, constant_values=big)
        neighbours = np.minimum.reduce(
            [padded[1:-1, 1:-1], padded[:-2, 1:-1], padded[2:, 1:-1], padded[1:-1, :-2], padded[1:-1, 2:]]
        )
        updated = np.where(mask, neighbours, 0)
        if np.array_equal(updated, labels):
            break
        labels = updated
    _, compact = np.unique(labels, return_inverse=True)  # 0 stays 0: it is the smallest
    return compact.reshape(mask.shape)


def describe_regions(labels: np.ndarray) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """Boxes (x0, y0, x1, y1), centroids (x, y) and a label text per region."""
    boxes, centroids, texts = [], [], []
    for region in range(1, labels.max() + 1):
        ys, xs = np.nonzero(labels == region)
        boxes.append([xs.min() - 1, ys.min() - 1, xs.max() + 1, ys.max() + 1])
        centroids.append([xs.mean(), ys.mean()])
        texts.append(f"#{region} {xs.size}px")
    return np.array(boxes).reshape(-1, 4), np.array(centroids).reshape(-1, 2), texts


@interactive(threshold=(0.45, [0.05, 0.95]), min_area=(20, [1, 200]))
def detect(img: np.ndarray, threshold: float = 0.45, min_area: int = 20) -> np.ndarray:
    """Threshold the brightness, keep regions of at least `min_area` pixels."""
    labels = connected_regions(img.mean(axis=-1) > threshold)
    areas = np.bincount(labels.ravel())
    small = np.flatnonzero(areas < min_area)
    labels[np.isin(labels, small[small > 0])] = 0
    _, labels = np.unique(labels, return_inverse=True)
    labels = labels.reshape(img.shape[:2])
    return labels


@interactive()
def draw_detections(img: np.ndarray, labels: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    boxes, centroids, texts = describe_regions(labels)
    count = len(boxes)
    colors = [draw.DEFAULT_COLORS[k % len(draw.DEFAULT_COLORS)] for k in range(count)]
    out = draw.boxes(img, boxes, labels=texts, color=colors, width=2)
    out = draw.points(out, centroids, color="red", radius=2.5)
    out = draw.text(out, f"{count} regions", (6, SIZE[0] - 6), anchor="bottom-left", size=16)
    layout.style("detections", title=f"Detections: {count}")
    regions = draw.mask(img, labels, alpha=0.6)  # same colour per region as its box
    layout.style("regions", title="Label mask")
    return out, regions


def overlay_pipeline() -> List[np.ndarray]:
    img = synthetic_blobs()
    labels = detect(img)
    detections, regions = draw_detections(img, labels)
    return [detections, regions]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Drawing detections with interactive_pipe.draw")
    parser.add_argument(
        "-b",
        "--backend",
        type=str,
        choices=["qt", "dpg", "gradio", "mpl", "nb"],
        default="qt",
        help="Backend to use (default: qt)",
    )
    args = parser.parse_args()
    interactive_pipeline(gui=args.backend, cache=True, name="Overlay demo")(overlay_pipeline)()
