"""Camera ISP: Bayer mosaic -> demosaic -> white balance -> gamma, checked against the ground truth.

What to look at: the error map (red = too bright, blue = too dark) lights up on edges and on the
fine stripes with nearest-neighbour demosaicking (zipper / colour aliasing) and turns uniformly
red or blue when the white balance gains are wrong. The PSNR in its title sums it up.
"""

from typing import Annotated, Literal

import numpy as np

from interactive_pipe import Image, interactive, interactive_pipeline, layout

SENSOR_GAINS = np.array([0.55, 1.0, 0.7])  # the sensor sees a greenish scene: WB must undo this


def make_scene(h=192, w=256):
    """Ground truth sRGB image: a hue ramp, a zone plate (fine detail) and a few flat patches."""
    y, x = np.mgrid[0:h, 0:w] / max(h, w)
    hue = np.stack([np.sin(6 * x + k * 2.1) * 0.4 + 0.5 for k in range(3)], axis=-1)
    zone = 0.5 + 0.45 * np.cos(250 * ((x - 0.75) ** 2 + (y - 0.25) ** 2))
    img = hue * (0.6 + 0.4 * zone[..., None])
    img[h // 2 :, : w // 3] = [0.8, 0.3, 0.2]
    img[h // 2 :, w // 3 : 2 * w // 3] = [0.5, 0.5, 0.5]
    return np.clip(img, 0, 1)


def conv3(img, k):
    """3x3 correlation with reflect padding (numpy only)."""
    p = np.pad(img, 1, mode="reflect")
    return sum(k[i, j] * p[i : i + img.shape[0], j : j + img.shape[1]] for i in range(3) for j in range(3))


@interactive
def mosaic(gt, noise: Annotated[float, (0.0, 0.05), "Sensor noise"] = 0.01):
    """Linearise, apply the sensor colour response, sample an RGGB Bayer pattern, add noise."""
    linear = gt**2.2 * SENSOR_GAINS
    raw = np.zeros(gt.shape[:2])
    raw[0::2, 0::2], raw[0::2, 1::2] = linear[0::2, 0::2, 0], linear[0::2, 1::2, 1]
    raw[1::2, 0::2], raw[1::2, 1::2] = linear[1::2, 0::2, 1], linear[1::2, 1::2, 2]
    return np.clip(raw + noise * np.random.default_rng(0).standard_normal(raw.shape), 0, 1)


@interactive
def demosaic(raw, method: Literal["bilinear", "nearest"] = "bilinear"):
    masks = np.zeros(raw.shape + (3,))
    masks[0::2, 0::2, 0] = masks[1::2, 1::2, 2] = 1
    masks[0::2, 1::2, 1] = masks[1::2, 0::2, 1] = 1
    if method == "nearest":
        k = np.array([[0, 0, 0], [0, 1, 1], [0, 1, 1]], float)
    else:
        k = np.array([[1, 2, 1], [2, 4, 2], [1, 2, 1]], float)
    return np.stack([conv3(raw * masks[..., c], k) / conv3(masks[..., c], k) for c in range(3)], axis=-1)


@interactive
def white_balance(
    rgb, red: Annotated[float, (0.5, 3.0), "Red gain"] = 1.8, blue: Annotated[float, (0.5, 3.0), "Blue gain"] = 1.4
):
    return np.clip(rgb * np.array([red, 1.0, blue]), 0, 1)


@interactive
def gamma(rgb, gamma: Annotated[float, (1.0, 3.0), "Gamma"] = 2.2):
    return rgb ** (1 / gamma)


@interactive
def compare(out, gt):
    layout.style("error", colormap="RdBu_r", center=0, colorbar=True, vmin=-0.3, vmax=0.3)
    psnr = 10 * np.log10(1 / np.mean((out - gt) ** 2))
    return Image((out - gt).mean(axis=-1), title=f"error, PSNR {psnr:.2f} dB")


@interactive_pipeline(gui="auto")
def camera_isp(gt):
    raw = mosaic(gt)
    rgb = demosaic(raw)
    balanced = white_balance(rgb)
    out = gamma(balanced)
    error = compare(out, gt)
    return [[out, gt], [raw, error]]


if __name__ == "__main__":
    camera_isp(make_scene())
