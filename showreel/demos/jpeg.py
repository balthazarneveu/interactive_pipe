"""JPEG in a nutshell (luminance only): 8x8 block DCT -> quantization -> inverse DCT.

Each 8x8 block is described by 64 cosine amplitudes. Dividing them by a step and
rounding is the only lossy operation: coarse steps turn most amplitudes into
zeros, which are cheap to store. Lower the quality and watch the rate drop, the
error grow and the 8x8 grid appear: each block is rounded on its own.
"""

import numpy as np

from interactive_pipe import Curve, interactive, interactive_pipeline, layout

N = 8
# DCT-II basis: row k is a cosine of frequency k sampled on N pixels (orthonormal, so the inverse is the transpose)
DCT = np.sqrt(2 / N) * np.cos(np.pi * (2 * np.arange(N)[None, :] + 1) * np.arange(N)[:, None] / (2 * N))
DCT[0] /= np.sqrt(2)
# Standard luminance table (JPEG annex K): the eye tolerates coarse steps on high frequencies (bottom right)
LUMA_STEPS = np.array(
    "16 11 10 16 24 40 51 61  12 12 14 19 26 58 60 55  14 13 16 24 40 57 69 56 "
    "14 17 22 29 51 87 80 62  18 22 37 56 68 109 103 77  24 35 55 64 81 104 113 92 "
    "49 64 78 87 103 121 120 101  72 92 95 98 112 100 103 99".split(),
    dtype=float,
).reshape(N, N)


# Filters without controls are plain functions: the pipeline at the bottom calls them like the decorated ones.
def to_blocks(img):  # (H, W) -> (H/8, W/8, 8, 8)
    return img.reshape(img.shape[0] // N, N, img.shape[1] // N, N).swapaxes(1, 2)


def from_blocks(blocks):
    return blocks.swapaxes(1, 2).reshape(blocks.shape[0] * N, blocks.shape[1] * N)


def quantize(coefficients, quality):
    scale = 5000 / quality if quality < 50 else 200 - 2 * quality  # libjpeg convention
    steps = np.clip(np.floor((LUMA_STEPS * scale + 50) / 100), 1, 255)
    return np.round(coefficients / steps), steps


def reconstruct(levels, steps):
    return np.clip((from_blocks(DCT.T @ (levels * steps) @ DCT) + 128) / 255, 0, 1)


def bits_per_pixel(levels):  # entropy of the quantized amplitudes: a proxy for the file size
    probabilities = np.unique(levels, return_counts=True)[1] / levels.size
    return -(probabilities * np.log2(probabilities)).sum()


def psnr(reference, img):
    return 10 * np.log10(1 / max(np.mean((reference - img) ** 2), 1e-12))


def test_image(size=256):
    layout.style("original", title="Original: smooth, edge, noise, chirp")
    y, x = np.mgrid[:size, :size] / size
    img = 0.3 + 0.4 * x  # smooth gradient: cheap to code
    img[np.hypot(x - 0.3, y - 0.35) < 0.2] = 0.9  # sharp edge: rings when high frequencies are dropped
    img[y > 0.7] = 0.5 + 0.4 * np.sin(2 * np.pi * x[y > 0.7] * 4 ** (1 + x[y > 0.7]))  # chirp: finer and finer detail
    texture = np.random.default_rng(0).normal(0, 0.08, img.shape)
    return np.clip(img + texture * ((x > 0.6) & (y < 0.7)), 0, 1)  # noise: the most expensive content


def block_dct(original):
    return DCT @ to_blocks(original * 255 - 128) @ DCT.T


@interactive(quality=(10, [1, 100], "JPEG quality"))
def encode(coefficients, quality=10):
    return quantize(coefficients, quality)


@interactive(gain=(10, [1, 50], "error amplification"))
def amplify_error(original, decoded, gain=10):
    layout.style("error", title=f"Error x{gain} (grey = none)")
    return np.clip(0.5 + gain * (decoded - original), 0, 1)


def surviving_coefficients(levels):
    layout.style("survivors", title=f"Non-zero amplitudes: {np.mean(levels != 0):.1%}")
    return from_blocks((levels != 0).astype(float))


def rate_distortion_sweep(original, coefficients):  # depends on the image only: cached, computed once
    sweep = [quantize(coefficients, quality) for quality in range(5, 100, 5)]
    return [bits_per_pixel(lvl) for lvl, _ in sweep], [psnr(original, reconstruct(lvl, steps)) for lvl, steps in sweep]


def rate_distortion(rates, psnrs, original, levels, decoded):
    rate, quality_db = bits_per_pixel(levels), psnr(original, decoded)
    layout.style("decoded", title=f"Decoded: {quality_db:.1f} dB, ~{rate:.2f} bit/pixel instead of 8")
    layout.style("rate_vs_distortion", title="Rate vs PSNR, quality 5 to 95 (red: current)")
    curves = [[rates, psnrs, "k.-"], [[rate], [quality_db], "ro"]]
    return Curve(curves, xlabel="rate (bit/pixel)", ylabel="PSNR (dB)", grid=True)


@interactive_pipeline(cache="graph")
def jpeg():
    original = test_image()
    coefficients = block_dct(original)
    levels, steps = encode(coefficients)
    decoded = reconstruct(levels, steps)
    error = amplify_error(original, decoded)
    survivors = surviving_coefficients(levels)
    rates, psnrs = rate_distortion_sweep(original, coefficients)
    rate_vs_distortion = rate_distortion(rates, psnrs, original, levels, decoded)
    return [[original, decoded, error], [survivors, rate_vs_distortion]]


if __name__ == "__main__":
    jpeg()
