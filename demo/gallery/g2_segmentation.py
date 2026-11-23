"""Segmentation debugging: two thresholds or k-means on a noisy three-region image.

What to look at: without smoothing, noise makes salt-and-pepper labels and the IoU in the overlay
title stays low; a radius of 2 fixes it; more smoothing blurs the edges and, as the ring (0.8) and
background (0.2) blend through the disc level (0.5), every ring edge gets a false "disc" band: the
confusion table shows it as ring / background pixels predicted as disc. Shift-drag a rectangle on
the overlay: the histogram of the region and the two thresholds are drawn; a region across a
boundary shows two modes, the thresholds belong in the valley between them. K-means finds the valley without being told.
"""

from typing import Annotated, Any, Dict, List, Literal

import numpy as np
from matplotlib.figure import Figure

from interactive_pipe import (
    RangeControl,
    RegionControl,
    Table,
    context,
    draw,
    interactive,
    interactive_pipeline,
    layout,
    to_pixels,
)

LEVELS = (0.2, 0.5, 0.8)  # true mean intensity of each class
COLORS = ((0.9, 0.2, 0.2), (0.2, 0.8, 0.2), (0.2, 0.4, 1.0))


def make_image(size=160, sigma=0.15, seed=1):
    """Noisy image and its ground-truth labels (0 background, 1 disc, 2 ring)."""
    y, x = np.mgrid[:size, :size] / size
    r = np.hypot(x - 0.55, y - 0.5)
    labels = np.where(r < 0.18, 1, np.where((r > 0.28) & (r < 0.38), 2, 0))
    labels[(x < 0.2) & (y < 0.3)] = 2
    noisy = np.take(LEVELS, labels) + sigma * np.random.default_rng(seed).standard_normal(labels.shape)
    return np.clip(noisy, 0, 1), labels


@interactive
def smooth(img, radius: Annotated[int, (0, 6), "smoothing radius"] = 2):
    padded, k = np.pad(img, radius, mode="edge"), 2 * radius + 1
    windows = np.lib.stride_tricks.sliding_window_view(padded, (k, k))
    return windows.mean(axis=(-2, -1))


@interactive(thresholds=RangeControl((0.35, 0.65), [0.0, 1.0]))
def segment(img, method: Literal["thresholds", "k-means"] = "thresholds", thresholds=(0.35, 0.65)):
    if method == "k-means":
        centers = np.array([0.1, 0.5, 0.9])
        for _ in range(10):
            labels = np.abs(img[..., None] - centers).argmin(axis=-1)
            centers = np.array([img[labels == k].mean() if np.any(labels == k) else centers[k] for k in range(3)])
        thresholds = tuple((centers[:-1] + centers[1:]) / 2)
    context["thresholds"] = thresholds  # for the histogram
    return np.digitize(img, thresholds)


@interactive
def evaluate(img, labels, truth):
    overlay = img
    for k, color in enumerate(COLORS):
        overlay = draw.mask(overlay, labels == k, color=color)
    iou = [np.sum((labels == k) & (truth == k)) / np.sum((labels == k) | (truth == k)) for k in range(3)]
    layout.style("overlay", title=f"mean IoU {np.mean(iou):.2f}")
    confusion: Dict[str, List[Any]] = {"truth \\ predicted": ["background", "disc", "ring"]}
    for k, name in enumerate(["background", "disc", "ring"]):
        confusion[name] = [int(np.sum((truth == t) & (labels == k))) for t in range(3)]
    return overlay, Table(confusion, title="confusion (pixels)")


@interactive(roi=RegionControl((0.4, 0.3, 0.9, 0.7), on="overlay"))
def histogram(img, roi=(0.4, 0.3, 0.9, 0.7)):
    x0, y0, x1, y1 = to_pixels(roi, img)
    ax = Figure(figsize=(4, 3)).subplots()
    ax.hist(img[y0:y1, x0:x1].ravel(), bins=50, range=(0, 1), color="gray")
    for t in context["thresholds"]:
        ax.axvline(t, color="k", linestyle="--")
    ax.set_title(f"region ({x0}, {y0}) - ({x1}, {y1})")
    ax.set_xlabel("intensity")
    return ax


@interactive_pipeline(gui="auto")
def g2_segmentation(img, truth):
    smoothed = smooth(img)
    labels = segment(smoothed)
    overlay, confusion = evaluate(img, labels, truth)
    hist = histogram(smoothed)
    return [[smoothed, overlay], [hist, confusion]]


if __name__ == "__main__":
    g2_segmentation(*make_image())
