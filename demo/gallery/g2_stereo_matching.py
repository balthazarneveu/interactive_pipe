"""Stereo vision: block matching between two views of a synthetic scene.

What to look at: the disparity map recovers the three depth planes (background 4 px, disc 9 px,
square 14 px); the error map (diverging, 0 = white) shows the "fattening" of the foreground at
depth edges, which grows with the window size, and the speckle due to sensor noise, which shrinks
with it. The left strip is seen by the left camera only: no match there.
A search range below 14 px clips the square. Click on the left view: the matching cost of that
pixel against every candidate disparity is plotted; a sharp single minimum = a reliable match.
"""

from typing import Annotated

import numpy as np

from interactive_pipe import Curve, PointControl, draw, interactive, interactive_pipeline, layout, to_pixels

H, W = 120, 160


def make_views(seed=0):
    """Left / right views and the ground-truth disparity of the left view (pixels)."""
    rng = np.random.default_rng(seed)
    texture = rng.random((H, W + 32))
    texture = 0.5 * texture + 0.25 * np.roll(texture, 1, axis=1) + 0.25 * np.roll(texture, 1, axis=0)
    y, x = np.mgrid[:H, :W]
    disparity = np.full((H, W), 4.0)
    disparity[(x - 50) ** 2 + (y - 60) ** 2 < 25**2] = 9.0
    disparity[30:80, 95:145] = 14.0
    left = texture[y, x + 16 - disparity.astype(int)]  # left(x) = right(x - d)
    right = texture[:, 16 : 16 + W]
    noise = 0.15 * rng.standard_normal((2, H, W))  # sensor noise: what a larger window averages out
    return np.clip(left + noise[0], 0, 1), np.clip(right + noise[1], 0, 1), disparity


def box_sum(img, radius):
    """Sum over a (2r+1)^2 window, edges replicated (integral image)."""
    padded = np.pad(img, radius, mode="edge")
    integral = np.pad(padded.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    k = 2 * radius + 1
    return integral[k:, k:] - integral[:-k, k:] - integral[k:, :-k] + integral[:-k, :-k]


@interactive
def block_match(
    left,
    right,
    window: Annotated[int, (1, 9), "window radius"] = 5,
    max_disparity: Annotated[int, (4, 24), "search range (px)"] = 20,
):
    costs = np.stack([box_sum((left - np.roll(right, d, axis=1)) ** 2, window) for d in range(max_disparity + 1)])
    for name in ("truth", "disparity"):  # truth is an input: styled by name from any filter
        layout.style(name, colormap="viridis", vmin=0, vmax=24, colorbar=True, unit="px")
    return costs.argmin(axis=0).astype(float), costs


@interactive
def disparity_error(disparity, truth):
    error = disparity - truth
    bad = np.mean(np.abs(error) > 1)
    title = f"error: {100 * bad:.1f}% pixels off by > 1 px"
    layout.style("error", title=title, colormap="RdBu_r", vmin=-8, vmax=8, colorbar="disparity error (px)")
    return error


@interactive(probe=PointControl((0.3, 0.5), on="marked"))
def cost_curve(left, costs, probe=(0.3, 0.5)):
    col, row = to_pixels(probe, left)
    curve = costs[:, row, col]
    best = int(curve.argmin())
    title = f"matching cost, minimum at {best} px"
    plot = Curve([[np.arange(len(curve)), curve, "b.-", f"pixel ({col}, {row})"]], xlabel="disparity (px)", title=title)
    return draw.points(left, [(col, row)], color="red"), plot


@interactive_pipeline(gui="auto")
def g2_stereo_matching(left, right, truth):
    disparity, costs = block_match(left, right)
    error = disparity_error(disparity, truth)
    marked, cost = cost_curve(left, costs)
    return [[marked, right, cost], [truth, disparity, error]]


if __name__ == "__main__":
    g2_stereo_matching(*make_views())
