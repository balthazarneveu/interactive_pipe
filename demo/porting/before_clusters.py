"""K-means on 2D blobs, PCA of the result, scatter coloured by cluster."""

import matplotlib.pyplot as plt
import numpy as np

N_POINTS = 300
N_CLUSTERS = 3
SPREAD = 0.6
ITERATIONS = 10

rng = np.random.default_rng(7)
centers = np.array([[0, 0], [3, 1], [1, 3]])
points = np.concatenate([c + SPREAD * rng.normal(size=(N_POINTS // 3, 2)) for c in centers])


def kmeans(x, k, iterations):
    means = x[rng.choice(len(x), k, replace=False)]
    for _ in range(iterations):
        labels = np.argmin(((x[:, None] - means[None]) ** 2).sum(-1), axis=1)
        means = np.array([x[labels == j].mean(0) if np.any(labels == j) else means[j] for j in range(k)])
    return labels, means


labels, means = kmeans(points, N_CLUSTERS, ITERATIONS)
centered = points - points.mean(0)
_, s, vt = np.linalg.svd(centered, full_matrices=False)
projected = centered @ vt.T

fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(10, 4))
ax0.scatter(points[:, 0], points[:, 1], c=labels, s=8, cmap="tab10")
ax0.plot(means[:, 0], means[:, 1], "kx", markersize=12)
ax0.set_title(f"k-means, k={N_CLUSTERS}")
ax1.scatter(projected[:, 0], projected[:, 1], c=labels, s=8, cmap="tab10")
ax1.set_title(f"PCA, explained {s[0] ** 2 / (s**2).sum():.0%}")
plt.show()
