"""Edge detector comparison: Sobel magnitude vs Laplacian, thresholded, for several thresholds."""

import matplotlib.pyplot as plt
import numpy as np

THRESHOLDS = [0.1, 0.2, 0.4]
SMOOTH = True

yy, xx = np.mgrid[0:96, 0:96]
img = ((xx - 48) ** 2 + (yy - 48) ** 2 < 30**2).astype(float)
img[10:30, 60:90] = 0.6
img += 0.05 * np.random.default_rng(2).normal(size=img.shape)


def convolve3(img, kernel):
    p = np.pad(img, 1, mode="edge")
    out = np.zeros_like(img)
    for dy in range(3):
        for dx in range(3):
            out += kernel[dy, dx] * p[dy : dy + img.shape[0], dx : dx + img.shape[1]]
    return out


if SMOOTH:
    img = convolve3(img, np.ones((3, 3)) / 9)

gx = convolve3(img, np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]]))
gy = convolve3(img, np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]]))
sobel = np.hypot(gx, gy)
sobel /= sobel.max()
lap = np.abs(convolve3(img, np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]])))
lap /= lap.max()

plt.figure(figsize=(9, 6))
for row, (name, edges) in enumerate([("sobel", sobel), ("laplacian", lap)]):
    for col, th in enumerate(THRESHOLDS):
        plt.subplot(2, len(THRESHOLDS), row * len(THRESHOLDS) + col + 1)
        plt.imshow(edges > th, cmap="gray")
        plt.title(f"{name} > {th}")
        plt.axis("off")
plt.show()
