"""Geometry / calibration: undistort a checkerboard seen through a homography and a radial lens distortion.

What to look at: the camera has an unknown radial distortion (k1, k2). Tune the estimated
coefficients until the corrected board has straight lines: the residual vectors (scaled up, drawn
from each true corner position) shrink and the RMS in the title drops. A wrong k1 sign gives
residuals pointing outward / inward that grow with the distance to the image centre.
"""

import numpy as np

from interactive_pipe import Image, draw, interactive, interactive_pipeline

H, W = 240, 320
K_TRUE = (-0.25, 0.08)  # the camera's distortion, to be recovered
HOMOGRAPHY = np.array([[1.1, 0.25, -0.1], [-0.15, 1.0, 0.05], [0.2, 0.15, 1.0]])  # board plane -> normalised image


def distort(u, k, iterations=10):
    """Inverse of undistort (fixed point): undistorted normalised coords -> distorted ones."""
    d = u.copy()
    for _ in range(iterations):
        r2 = (d**2).sum(-1, keepdims=True)
        d = u / (1 + k[0] * r2 + k[1] * r2**2)
    return np.where(np.abs(undistort(d, k) - u).max(-1, keepdims=True) < 1e-3, d, np.nan)  # NaN: not invertible


def undistort(d, k):
    r2 = (d**2).sum(-1, keepdims=True)
    return d * (1 + k[0] * r2 + k[1] * r2**2)


def to_pixels(n):
    return n * W / 2 + np.array([W / 2, H / 2])


def pixel_grid():
    y, x = np.mgrid[0:H, 0:W]
    return (np.stack([x, y], -1) - np.array([W / 2, H / 2])) / (W / 2)


def board(u):
    """Checkerboard seen at undistorted normalised coords u (8x6 squares on the unit plane)."""
    p = np.concatenate([u, np.ones(u.shape[:-1] + (1,))], -1) @ np.linalg.inv(HOMOGRAPHY).T
    bx, by = p[..., 0] / p[..., 2], p[..., 1] / p[..., 2]
    inside = (np.abs(bx) < 0.8) & (np.abs(by) < 0.6)  # NaN coordinates fall outside: gray
    return np.where(inside, ((np.floor(bx * 5) + np.floor(by * 5)) % 2) * 0.8 + 0.1, 0.5)


def true_corners():
    bx, by = np.meshgrid(np.arange(-3, 4) / 5, np.arange(-2, 3) / 5)
    p = np.stack([bx, by, np.ones_like(bx)], -1).reshape(-1, 3) @ HOMOGRAPHY.T
    return p[:, :2] / p[:, 2:]


@interactive()
def capture():
    return board(undistort(pixel_grid(), K_TRUE))


@interactive(k1=(0.0, [-0.5, 0.5]), k2=(0.0, [-0.2, 0.2]), arrow_scale=(3.0, [1.0, 20.0]))
def correct(k1=0.0, k2=0.0, arrow_scale=3.0):
    corrected = board(undistort(distort(pixel_grid(), (k1, k2)), K_TRUE))
    truth = true_corners()
    estimated = undistort(distort(truth, K_TRUE), (k1, k2))  # detected corners, undistorted with (k1, k2)
    start, end = to_pixels(truth), to_pixels(truth + arrow_scale * (estimated - truth))
    rms = np.sqrt(((to_pixels(estimated) - start) ** 2).sum(-1).mean())
    out = draw.lines(np.dstack([corrected] * 3), np.stack([start, end], 1), color="red", width=2)
    out = draw.points(out, start, color="lime", radius=2)
    return Image(out, title=f"corrected, residual RMS {rms:.2f} px (x{arrow_scale:g})")


@interactive_pipeline(gui="auto")
def lens_calibration():
    captured = capture()
    corrected = correct()
    return captured, corrected


if __name__ == "__main__":
    lens_calibration()
