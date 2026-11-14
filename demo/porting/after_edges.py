"""Edge detectors with a threshold slider (port of before_edges.py).

The loop over thresholds becomes a slider; the 2 x 3 grid of the original is
``edges.sweep(path, threshold=[0.1, 0.2, 0.4], output=["sobel", "laplacian"])``."""

import numpy as np

from interactive_pipe import interactive, interactive_pipeline


def convolve3(img, kernel):
    p = np.pad(img, 1, mode="edge")
    out = np.zeros_like(img)
    for dy in range(3):
        for dx in range(3):
            out += kernel[dy, dx] * p[dy : dy + img.shape[0], dx : dx + img.shape[1]]
    return out


@interactive(smooth=True)
def smooth_image(img, smooth=True):
    return convolve3(img, np.ones((3, 3)) / 9) if smooth else img


@interactive(threshold=(0.2, [0.0, 1.0]))
def detect(img, threshold=0.2):
    gx = convolve3(img, np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]]))
    gy = convolve3(img, np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]]))
    sobel = np.hypot(gx, gy)
    sobel /= sobel.max()
    lap = np.abs(convolve3(img, np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]])))
    lap /= lap.max()
    return sobel > threshold, lap > threshold


@interactive_pipeline(gui="auto")
def edges(img):
    smoothed = smooth_image(img)
    sobel, laplacian = detect(smoothed)
    return smoothed, sobel, laplacian


def synthetic_image():
    yy, xx = np.mgrid[0:96, 0:96]
    img = ((xx - 48) ** 2 + (yy - 48) ** 2 < 30**2).astype(float)
    img[10:30, 60:90] = 0.6
    return img + 0.05 * np.random.default_rng(2).normal(size=img.shape)


if __name__ == "__main__":
    edges(synthetic_image())
