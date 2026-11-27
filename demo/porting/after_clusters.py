"""K-means and PCA scatter with sliders (port of before_clusters.py)."""

from typing import Tuple

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure

from interactive_pipe import interactive, interactive_pipeline

CENTERS = np.array([[0, 0], [3, 1], [1, 3]])


@interactive(n_points=(300, [30, 1000]), spread=(0.6, [0.1, 2.0]))
def make_blobs(n_points: int = 300, spread: float = 0.6) -> np.ndarray:
    rng = np.random.default_rng(7)
    return np.concatenate([c + spread * rng.normal(size=(n_points // 3, 2)) for c in CENTERS])


@interactive(n_clusters=(3, [1, 8]), iterations=(10, [1, 30]))
def kmeans(x: np.ndarray, n_clusters: int = 3, iterations: int = 10) -> Tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(0)
    means = x[rng.choice(len(x), n_clusters, replace=False)]
    for _ in range(iterations):
        labels = np.argmin(((x[:, None] - means[None]) ** 2).sum(-1), axis=1)
        means = np.array([x[labels == j].mean(0) if np.any(labels == j) else means[j] for j in range(n_clusters)])
    return labels, means


@interactive()
def scatter(points: np.ndarray, labels: np.ndarray, means: np.ndarray) -> Figure:
    centered = points - points.mean(0)
    _, s, vt = np.linalg.svd(centered, full_matrices=False)
    projected = centered @ vt.T
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(10, 4))  # the original pyplot code, kept as is
    ax0.scatter(points[:, 0], points[:, 1], c=labels, s=8, cmap="tab10")
    ax0.plot(means[:, 0], means[:, 1], "kx", markersize=12)
    ax0.set_title(f"k-means, k={len(means)}")
    ax1.scatter(projected[:, 0], projected[:, 1], c=labels, s=8, cmap="tab10")
    ax1.set_title(f"PCA, explained {s[0] ** 2 / (s**2).sum():.0%}")
    return fig


@interactive_pipeline(gui="auto")
def clusters() -> Figure:
    points = make_blobs()
    labels, means = kmeans(points)
    fig = scatter(points, labels, means)
    return fig


if __name__ == "__main__":
    clusters()
