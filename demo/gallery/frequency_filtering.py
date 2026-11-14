"""Frequency-domain filtering: a band-pass mask between two radii, applied to the image spectrum.

What to look at: the log-spectrum shows the periodic stripe pattern as two bright peaks; move the
band so that it keeps them (the filtered image becomes the stripes alone) or excludes them (the
stripes vanish). The radial power profile shows where the band sits in the spectrum, and the
ringing that a hard mask edge produces as you lower the softness.
"""

import numpy as np
from matplotlib.figure import Figure

from interactive_pipe import RangeControl, context, interactive, interactive_pipeline, layout


def make_image(n=256):
    """Gray scene: smooth blobs + a periodic stripe pattern + white noise."""
    y, x = np.mgrid[0:n, 0:n] / n
    blobs = np.exp(-((x - 0.3) ** 2 + (y - 0.4) ** 2) / 0.02) + 0.6 * np.exp(-((x - 0.7) ** 2 + (y - 0.7) ** 2) / 0.01)
    stripes = 0.15 * np.sin(2 * np.pi * (40 * x + 25 * y))
    noise = 0.05 * np.random.default_rng(0).standard_normal((n, n))
    return np.clip(0.2 + 0.6 * blobs + stripes + noise, 0, 1)


def radius(shape):
    """Normalised frequency radius of every FFT bin (0 at DC, 0.5 at Nyquist along an axis)."""
    fy, fx = np.meshgrid(
        np.fft.fftshift(np.fft.fftfreq(shape[0])), np.fft.fftshift(np.fft.fftfreq(shape[1])), indexing="ij"
    )
    return np.hypot(fx, fy)


@interactive()
def spectrum(img):
    layout.style("log_spectrum", title="log10 |FFT|", colormap="magma", vmin=1.0, colorbar=True)
    f = np.fft.fftshift(np.fft.fft2(img))
    return f, np.log10(np.abs(f) + 1e-6)


@interactive(band=RangeControl((0.1, 0.3), [0.0, 0.71], name="band (cycles/px)"), softness=(0.01, [0.0, 0.05]))
def band_pass(f, band=(0.1, 0.3), softness=0.01):
    r = radius(f.shape)
    low, high = context["band"] = band  # one slider, read again by radial_profile
    s = max(softness, 1e-4)
    mask = 1 / (1 + np.exp(-(r - low) / s)) * 1 / (1 + np.exp((r - high) / s))
    return f * mask, mask


@interactive()
def inverse(f):
    out = np.real(np.fft.ifft2(np.fft.ifftshift(f)))
    return (out - out.min()) / (np.ptp(out) + 1e-12)


@interactive()
def radial_profile(f):
    r = radius(f.shape).ravel()
    bins = np.linspace(0, 0.71, 72)
    idx = np.digitize(r, bins)
    power = np.array(
        [np.mean(np.abs(f.ravel()[idx == i]) ** 2) if np.any(idx == i) else np.nan for i in range(1, len(bins))]
    )
    fig = Figure(figsize=(5, 3.5))
    ax = fig.subplots()
    ax.semilogy(bins[1:], power)
    ax.axvspan(*context["band"], color="tab:orange", alpha=0.25, label="band")
    ax.set_xlabel("radius (cycles / pixel)")
    ax.set_ylabel("mean power")
    ax.legend()
    fig.tight_layout()
    return fig


@interactive_pipeline(gui="auto")
def frequency_filtering(img):
    f, log_spectrum = spectrum(img)
    filtered_f, mask = band_pass(f)
    filtered = inverse(filtered_f)
    profile = radial_profile(f)
    return [[img, log_spectrum, mask], [filtered, profile]]


if __name__ == "__main__":
    frequency_filtering(make_image())
