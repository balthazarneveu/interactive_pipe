"""Spectral bias: why coordinate networks need a positional encoding.

An image is fitted as a function of its pixel coordinates (x, y) in [0, 1]^2, from a random subset of
its pixels. The coordinates first go through random Fourier features
    gamma(p) = [cos(2 pi B p), sin(2 pi B p)] / sqrt(n),   B: n x 2, entries ~ N(0, scale^2)
and a linear model on gamma(p) is solved in closed form (ridge least squares): the last layer of a
coordinate network, without the training loop. The scale sets which frequencies the model can use:
- too low (~1): only smooth functions, blur everywhere, both PSNRs low (under-fit);
- around 8: edges and stripes come back on the held-out pixels too;
- too high (~32): every sample is fitted exactly, but the function oscillates in between: the
  training PSNR soars while the held-out PSNR collapses (over-fit).
With fewer features than samples (raise the share), the samples can no longer all be matched exactly.
Raw (x, y) coordinates with a linear model can only give a plane: the scale -> 0 limit of this demo.
"""

import numpy as np

from interactive_pipe import Curve, interactive, interactive_pipeline, layout

SIZE, RIDGE = 96, 1e-3
SWEEP = 2.0 ** np.arange(7)  # frequency scales 1, 2, 4 ... 64 for the PSNR curve


def edge(signed_distance):  # 0 -> 1 across a sharp (about 1 pixel) but anti-aliased edge
    return 1 / (1 + np.exp(-signed_distance * SIZE / 0.7))


def target():
    y, x = np.mgrid[:SIZE, :SIZE] / SIZE
    img = 0.3 + 0.3 * x + 0.1 * np.cos(2 * np.pi * y)  # smooth background
    disc = edge(0.2 - np.hypot(x - 0.32, y - 0.38))
    img = img * (1 - disc) + 0.85 * disc
    patch = edge(np.minimum(x - 0.6, y - 0.55))  # fine detail: oblique stripes, period ~14 pixels
    return img * (1 - patch) + patch * (0.5 + 0.3 * np.sin(2 * np.pi * 5 * (x + y)))


@interactive(share=(0.1, [0.02, 0.2], "share of pixels used for fitting"))
def pick_training_pixels(img, share=0.1):
    is_train = np.random.default_rng(0).random(img.size) < share  # nested: a larger share adds pixels
    layout.style("samples", title=f"Target: the fit only sees the {is_train.sum()} bright pixels ({share:.0%})")
    return is_train


@interactive(n_features=(512, [32, 640], "number of Fourier features"))
def draw_frequencies(n_features=512):
    return np.random.default_rng(1).normal(size=(n_features, 2))  # unit scale: the slider stretches them


def fit(img, is_train, frequencies, scale):
    # exp(2i pi b.p) = exp(2i pi b_y y) exp(2i pi b_x x): on a grid, cos and sin come from 2 x SIZE exponentials
    waves = [np.exp(2j * np.pi * np.outer(np.arange(SIZE) / SIZE, scale * b)) for b in frequencies.T]
    z = (waves[0][:, None, :] * waves[1][None, :, :]).reshape(SIZE * SIZE, -1)
    features = np.concatenate([z.real, z.imag], 1) / np.sqrt(len(frequencies))  # each row has unit norm
    a, b = features[is_train], img.ravel()[is_train]
    # Ridge least squares, solved in the smaller of the two spaces (same solution). RIDGE = 1e-3 keeps the
    # condition number below n_samples / RIDGE (~1e6) when the samples are interpolated exactly.
    if len(a) < a.shape[1]:
        weights = a.T @ np.linalg.solve(a @ a.T + RIDGE * np.eye(len(a)), b - b.mean())
    else:
        weights = np.linalg.solve(a.T @ a + RIDGE * np.eye(a.shape[1]), a.T @ (b - b.mean()))
    prediction = features @ weights + b.mean()  # the mean plays the role of an unregularized bias
    psnr = [10 * np.log10(1 / np.mean((prediction - img.ravel())[m] ** 2)) for m in (is_train, ~is_train)]
    return prediction.reshape(img.shape), psnr


def show_samples(img, is_train):
    return img * np.where(is_train.reshape(img.shape), 1.0, 0.3)  # held-out pixels dimmed


@interactive(scale=(8.0, [0.5, 64.0], "frequency scale"))
def reconstruct(img, is_train, frequencies, scale=8.0):
    prediction, (train, held_out) = fit(img, is_train, frequencies, scale)
    layout.style("reconstruction", title=f"Fit: {train:.1f} dB on fitted pixels, {held_out:.1f} dB held out")
    layout.style("error", title="Error (blue: too dark, red: too bright)", colormap="RdBu_r", vmin=-0.3, vmax=0.3)
    return np.clip(prediction, 0, 1), prediction - img, np.array([scale, train, held_out])


def sweep_scales(img, is_train, frequencies):  # independent of the scale slider: cached by cache="graph"
    return np.array([fit(img, is_train, frequencies, scale)[1] for scale in SWEEP])


def plot_sweep(psnrs, current):
    return Curve(
        [
            [np.log2(SWEEP), psnrs[:, 0], "b.-", "fitted pixels"],
            [np.log2(SWEEP), psnrs[:, 1], "r.-", "held-out pixels"],
            [[np.log2(current[0])] * 2, current[1:], "ko", f"scale {current[0]:.1f}"],
        ],
        title="PSNR vs frequency scale: under-fit | sweet spot | over-fit",
        xlabel="log2(frequency scale)",
        ylabel="PSNR (dB)",
        ylim=(0, 60),
        grid=True,
    )


@interactive_pipeline(gui="auto", cache="graph", name="Random Fourier features")
def fourier_features():
    image = target()
    is_train = pick_training_pixels(image)
    frequencies = draw_frequencies()
    samples = show_samples(image, is_train)
    reconstruction, error, current = reconstruct(image, is_train, frequencies)
    psnrs = sweep_scales(image, is_train, frequencies)
    psnr_curve = plot_sweep(psnrs, current)
    return [[samples, reconstruction], [error, psnr_curve]]


if __name__ == "__main__":
    fourier_features()
