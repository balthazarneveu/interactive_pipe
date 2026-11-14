"""Aliasing: low-pass before you decimate.

A zone plate is a chirp whose spatial frequency grows linearly with the distance
to the centre, reaching 0.5 cycle/pixel (the Nyquist limit) in the corners.
Keeping one pixel out of `factor` lowers the Nyquist limit to 0.5 / factor:
every ring beyond the red circle can no longer be represented and folds back as
fake low-frequency rings (moire). Blurring first removes those frequencies.
"""

import numpy as np

from interactive_pipe import interactive, interactive_pipeline, layout

SIZE = 512


@interactive()
def zone_plate():
    y, x = np.mgrid[:SIZE, :SIZE] - (SIZE - 1) / 2
    r_max = np.hypot(SIZE / 2, SIZE / 2)
    # local frequency d(phase)/dr / 2pi = r / (2 r_max): 0.5 cycle/pixel at the corners
    return 0.5 + 0.5 * np.cos(np.pi * (x**2 + y**2) / (2 * r_max))


@interactive(factor=(4, [1, 8], "downsampling factor"))
def downsampling_factor(factor=4):
    layout.style("original", title=f"Original: outside the circle, rings are too fine for 1/{factor} sampling")
    layout.style("naive", title=f"Naive: keep 1 pixel out of {factor}")
    return factor


@interactive(sigma=(0.5, [0.0, 1.5], "pre-filter blur (sigma, output pixels)"))
def low_pass(img, factor, sigma=0.5):
    """Gaussian blur, applied in the Fourier domain. sigma is in output pixels: ~0.5 is the sweet spot,
    less lets aliasing through, more blurs away detail the small image could have kept."""
    layout.style("anti_aliased", title=f"Gaussian blur (sigma = {sigma * factor:.1f} px), then keep 1 out of {factor}")
    pad = img.shape[0] // 2  # mirror padding: the FFT would otherwise wrap the borders around
    padded = np.pad(img, pad, mode="reflect")
    fy, fx = np.fft.fftfreq(padded.shape[0])[:, None], np.fft.rfftfreq(padded.shape[1])[None, :]
    transfer = np.exp(-2 * (np.pi * sigma * factor) ** 2 * (fx**2 + fy**2))
    return np.fft.irfft2(np.fft.rfft2(padded) * transfer, s=padded.shape)[pad:-pad, pad:-pad]


@interactive()
def decimate(img, factor):
    """Keep one pixel out of `factor`, then repeat it so that the result keeps the original display size."""
    small = img[::factor, ::factor]
    return np.repeat(np.repeat(small, factor, axis=0), factor, axis=1)[: img.shape[0], : img.shape[1]]


@interactive()
def mark_nyquist(img, factor):
    """Draw the radius where the zone plate frequency reaches the new Nyquist limit 0.5 / factor."""
    y, x = np.mgrid[: img.shape[0], : img.shape[1]] - (np.array(img.shape)[:, None, None] - 1) / 2
    on_circle = np.abs(np.hypot(x, y) - np.hypot(*img.shape) / 2 / factor) < 1.5
    rgb = np.repeat(img[..., None], 3, axis=-1)
    rgb[on_circle] = [1.0, 0.0, 0.0]
    return rgb


@interactive_pipeline(cache="graph")
def aliasing():
    pattern = zone_plate()
    factor = downsampling_factor()
    original = mark_nyquist(pattern, factor)
    naive = decimate(pattern, factor)
    smoothed = low_pass(pattern, factor)
    anti_aliased = decimate(smoothed, factor)
    return [original, naive, anti_aliased]


if __name__ == "__main__":
    aliasing()
