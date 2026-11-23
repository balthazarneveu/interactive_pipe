"""Frequency-domain filtering: a band-pass mask between two radii, applied to the image spectrum.

What to look at: the log-spectrum shows the periodic stripe pattern as two bright peaks; move the
band so that it keeps them (the filtered image becomes the stripes alone) or excludes them (the
stripes vanish). The radial power profile shows where the band sits in the spectrum, and the
ringing that a hard mask edge produces as you lower the softness.
"""

from typing import Any, List, Tuple

import numpy as np
from matplotlib.figure import Figure

from interactive_pipe import RangeControl, interactive, interactive_pipeline, layout


def make_image(n: int = 256) -> np.ndarray:
    """Gray scene: smooth blobs + a periodic stripe pattern + white noise."""
    y, x = np.mgrid[0:n, 0:n] / n
    blobs = np.exp(-((x - 0.3) ** 2 + (y - 0.4) ** 2) / 0.02) + 0.6 * np.exp(-((x - 0.7) ** 2 + (y - 0.7) ** 2) / 0.01)
    stripes = 0.15 * np.sin(2 * np.pi * (40 * x + 25 * y))
    noise = 0.05 * np.random.default_rng(0).standard_normal((n, n))
    return np.clip(0.2 + 0.6 * blobs + stripes + noise, 0, 1)


def radius(shape: Tuple[int, ...]) -> np.ndarray:
    """Normalised frequency radius of every FFT bin (0 at DC, 0.5 at Nyquist along an axis)."""
    fy, fx = np.meshgrid(
        np.fft.fftshift(np.fft.fftfreq(shape[0])), np.fft.fftshift(np.fft.fftfreq(shape[1])), indexing="ij"
    )
    return np.hypot(fx, fy)


@interactive()
def spectrum(img: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    layout.style("log_spectrum", title="spectrum", colormap="magma", vmin=1.0, colorbar="log10 |FFT|")
    f = np.fft.fftshift(np.fft.fft2(img))
    return f, np.log10(np.abs(f) + 1e-6)


BAND = RangeControl((0.1, 0.3), [0.0, 0.71], name="band (cycles/px)")  # one slider, used by two filters


@interactive(band=BAND, softness=(0.01, [0.0, 0.05]))
def band_pass(
    f: np.ndarray, band: Tuple[float, float] = (0.1, 0.3), softness: float = 0.01
) -> Tuple[np.ndarray, np.ndarray]:
    r, s = radius(f.shape), max(softness, 1e-4)
    mask = 1 / (1 + np.exp(-(r - band[0]) / s)) / (1 + np.exp((r - band[1]) / s))
    return f * mask, mask


@interactive()
def inverse(f: np.ndarray) -> np.ndarray:
    out = np.real(np.fft.ifft2(np.fft.ifftshift(f)))
    return (out - out.min()) / (np.ptp(out) + 1e-12)


@interactive(band=BAND)
def radial_profile(f: np.ndarray, band: Tuple[float, float] = (0.1, 0.3)) -> Figure:
    idx = np.round(radius(f.shape) * 100).astype(int).ravel()  # 0.01 cycle/px bins
    power = np.bincount(idx, np.abs(f.ravel()) ** 2) / np.maximum(np.bincount(idx), 1)
    fig = Figure(figsize=(5, 3.5), layout="tight")
    ax = fig.subplots()
    ax.semilogy(np.arange(power.size) / 100, power)
    ax.axvspan(*band, color="tab:orange", alpha=0.25, label="band")
    ax.set(xlabel="radius (cycles / pixel)", ylabel="mean power")
    ax.legend()
    return fig


@interactive_pipeline(gui="auto")
def frequency_filtering(img: np.ndarray) -> List[List[Any]]:
    f, log_spectrum = spectrum(img)
    filtered_f, mask = band_pass(f)
    filtered = inverse(filtered_f)
    profile = radial_profile(f)
    return [[img, log_spectrum, mask], [filtered, profile]]


if __name__ == "__main__":
    frequency_filtering(make_image())
