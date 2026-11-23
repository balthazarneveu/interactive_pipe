"""Image compression: 8x8 block DCT with a JPEG-style quantisation table scaled by a quality factor.

What to look at: at low quality the error map shows ringing around the edges and the stripes, and
the 8x8 blocks: at quality 5 even the smooth gradient becomes a staircase of flat blocks. Rate
(entropy of the quantised coefficients, bits per pixel) and PSNR both grow with the quality: the
rate-distortion curve marks the current point. "zero high frequencies" keeps only the 3x3 lowest
frequencies of each block: the stripes, a high frequency, disappear.
"""

from typing import Any, List, Tuple

import numpy as np

from interactive_pipe import Control, Curve, Table, interactive, interactive_pipeline, layout

B = 8
k, n = np.meshgrid(np.arange(B), np.arange(B), indexing="ij")
DCT = np.sqrt(2 / B) * np.cos(np.pi * (2 * n + 1) * k / (2 * B))
DCT[0] /= np.sqrt(2)  # orthonormal DCT-II matrix
QUALITY = Control(50, [1, 100], name="quality")  # shared by both filters
ZERO_HIGH = Control(False, name="zero high frequencies")
JPEG_LUMA = 1 + (np.add.outer(np.arange(B), np.arange(B)) * 6 + 10)  # simplified: grows with frequency


def make_image(size: int = 128) -> np.ndarray:
    y, x = np.mgrid[:size, :size] / size
    img: np.ndarray = 0.2 + 0.6 * x  # smooth gradient
    img[(x - 0.7) ** 2 + (y - 0.3) ** 2 < 0.04] = 0.9  # sharp-edged disc
    img[y > 0.6] = 0.5 + 0.3 * np.sin(2 * np.pi * 40 * x[y > 0.6])  # fine stripes
    img[(y > 0.1) & (y < 0.45) & (x > 0.1) & (x < 0.4)] = 0.15  # dark patch
    return img


def code(img: np.ndarray, quality: int, zero_high: bool) -> Tuple[np.ndarray, np.ndarray]:
    """Quantised DCT coefficients per block, shape (H/8, W/8, 8, 8), and the reconstruction."""
    scale = 5000 / quality if quality < 50 else 200 - 2 * quality
    step = np.maximum(JPEG_LUMA * scale / 100, 1) / 255
    blocks = img.reshape(img.shape[0] // B, B, img.shape[1] // B, B).transpose(0, 2, 1, 3)
    coefs = np.round(DCT @ blocks @ DCT.T / step)
    if zero_high:
        coefs[..., 3:, :] = coefs[..., :, 3:] = 0
    recon = (DCT.T @ (coefs * step) @ DCT).transpose(0, 2, 1, 3).reshape(img.shape)
    return coefs, np.clip(recon, 0, 1)


def rate_psnr(img: np.ndarray, coefs: np.ndarray, recon: np.ndarray) -> Tuple[float, float]:
    _, counts = np.unique(coefs, return_counts=True)
    p = counts / counts.sum()
    return float(-(p * np.log2(p)).sum()), float(10 * np.log10(1 / np.mean((recon - img) ** 2)))


@interactive(quality=QUALITY, zero_high=ZERO_HIGH)
def compress(img: np.ndarray, quality: int = 50, zero_high: bool = False) -> Tuple[np.ndarray, np.ndarray]:
    coefs, recon = code(img, quality, zero_high)
    rate, psnr = rate_psnr(img, coefs, recon)
    layout.style("reconstruction", title=f"quality {quality}: {rate:.2f} bpp, PSNR {psnr:.1f} dB")
    layout.style("error", colormap="RdBu_r", center=0, vmin=-0.2, vmax=0.2, colorbar="reconstruction - original")
    return recon, recon - img


@interactive(quality=QUALITY, zero_high=ZERO_HIGH)
def rate_distortion(img: np.ndarray, quality: int = 50, zero_high: bool = False) -> Tuple[Curve, Table]:
    qualities = [5, 10, 20, 30, 50, 70, 85, 95]
    points = np.array([rate_psnr(img, *code(img, q, zero_high)) for q in qualities])
    current = rate_psnr(img, *code(img, quality, zero_high))
    curve = Curve(
        [[points[:, 0], points[:, 1], "b.-", "quality 5 ... 95"], [[current[0]], [current[1]], "ro", "current"]],
        xlabel="rate (bits per pixel)",
        ylabel="PSNR (dB)",
        grid=True,
    )
    table = Table(
        {"quality": qualities, "rate (bpp)": np.round(points[:, 0], 2), "PSNR (dB)": np.round(points[:, 1], 1)}
    )
    return curve, table


@interactive_pipeline(gui="auto")
def g2_dct_compression(img: np.ndarray) -> List[List[Any]]:
    reconstruction, error = compress(img)
    rd, rd_table = rate_distortion(img)
    return [[img, reconstruction, error], [rd, rd_table]]


if __name__ == "__main__":
    g2_dct_compression(make_image())
