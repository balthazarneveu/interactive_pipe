"""Diffusion without training: the data is a Gaussian mixture, so the score of every noised marginal is exact.

Forward (variance preserving): x_t = alpha_t x_0 + sigma_t eps, alpha_t^2 + sigma_t^2 = 1, t from 0 (data) to 1 (noise).
Data: 8 modes mu_k on a ring, each N(mu_k, s^2 I), equal weights. Noising a Gaussian keeps it Gaussian, so
    p_t(x) = 1/8 sum_k N(x; alpha_t mu_k, v_t I),   v_t = alpha_t^2 s^2 + sigma_t^2
    r_k(x) = softmax_k(-|x - alpha_t mu_k|^2 / 2 v_t)        (which mode x_t probably came from)
    E[x_0 | x_t] = sum_k r_k (mu_k + alpha_t s^2 / v_t (x - alpha_t mu_k))   (Gaussian posterior, per mode)
    score  grad log p_t(x) = sum_k r_k (alpha_t mu_k - x) / v_t = (alpha_t E[x_0 | x_t] - x) / sigma_t^2  (Tweedie)
The sampler starts from pure noise and walks t = 1 -> 0 in N uniform steps (DDIM): predict x_0, keep the predicted
noise, re-noise to the next time (ancestral: part of that noise is drawn afresh, as in DDPM). With too few steps
the last prediction is an average over several modes: points land between the modes. Once they land on the modes
they are first too concentrated (the last step returns the posterior mean E[x_0 | x_t], narrower than a mode);
with ~200 steps the mean distance to the modes is within a few % of the data's.
Structure appears when the SNR alpha/sigma reaches the mode spacing (~0 dB): the linear schedule gets there late
(t ~ 0.3), so most of its uniform steps are spent on pure noise; the cosine schedule spreads them better.

    python diffusion.py             # interactive window (press v to export a GIF)
    python diffusion.py out.gif     # no window: render the reverse process to a GIF
"""

import sys

import numpy as np

from interactive_pipe import Curve, TimeControl, export_animation, interactive, interactive_pipeline, layout

MODES, RADIUS, WIDTH, POINTS = 8, 1.5, 0.1, 3000
MU = RADIUS * np.stack([np.cos(2 * np.pi * np.arange(MODES) / MODES), np.sin(2 * np.pi * np.arange(MODES) / MODES)], 1)
# splatting grid over [-EXTENT, EXTENT]^2, displayed ZOOM times larger; a PERIOD-second loop at FPS
BINS, EXTENT, ZOOM, PERIOD, FPS = 96, 2.4, 4, 8.0, 10
X, Y = np.meshgrid(*[(np.arange(BINS) + 0.5) / BINS * 2 * EXTENT - EXTENT] * 2)
RINGS = np.abs(np.hypot(X[..., None] - MU[:, 0], -Y[..., None] - MU[:, 1]) - 3 * WIDTH).min(-1) < 0.03
GIF = next((arg for arg in sys.argv[1:] if arg.endswith(".gif")), None)


def schedule_at(t, schedule):
    if schedule == "linear":  # beta(t) = 0.1 + 19.9 t (DDPM / Song et al.), alpha_t = exp(-1/2 int_0^t beta)
        alpha = np.exp(-0.5 * (0.1 * t + 0.5 * 19.9 * t**2))
    else:  # cosine (Nichol & Dhariwal), offset 0.008
        alpha = np.cos((t + 0.008) / 1.008 * np.pi / 2) / np.cos(0.008 / 1.008 * np.pi / 2)
    return alpha, np.sqrt(1 - alpha**2)


def denoise(x, alpha, sigma):
    """Exact E[x_0 | x_t] for the Gaussian mixture (see the header)."""
    v = alpha**2 * WIDTH**2 + sigma**2
    logits = alpha * MU @ x.T / v  # (mode, point) = -|x - alpha mu_k|^2 / 2v + const: all |mu_k| are equal
    r = np.exp(logits - logits.max(0))
    m = (MU.T @ r / r.sum(0)).T  # sum_k r_k mu_k
    return m + alpha * WIDTH**2 / v * (x - alpha * m)


def dataset():
    rng = np.random.default_rng(0)
    return MU[rng.integers(MODES, size=POINTS)] + WIDTH * rng.normal(size=(POINTS, 2)), rng.normal(size=(POINTS, 2))


@interactive(
    steps=(10, [1, 200], "sampling steps"),
    schedule=("linear", ["linear", "cosine"], "noise schedule"),
    sampler=("DDIM", ["DDIM", "ancestral"], "sampler"),
)
def reverse_process(steps=10, schedule="linear", sampler="DDIM"):  # also passes the schedule on to the views
    rng = np.random.default_rng(1)
    x, times = rng.standard_normal((POINTS, 2)), np.linspace(1, 0, steps + 1)
    trajectory = [x]
    for t, s in zip(times[:-1], times[1:]):
        (alpha_t, sigma_t), (alpha_s, sigma_s) = schedule_at(t, schedule), schedule_at(s, schedule)
        x0 = denoise(x, alpha_t, sigma_t)
        eps = (x - alpha_t * x0) / sigma_t
        # ancestral = DDPM posterior: part of the noise at time s is fresh instead of the predicted one
        fresh = sigma_s * np.sqrt(1 - (alpha_t * sigma_s / (alpha_s * sigma_t)) ** 2) if sampler != "DDIM" else 0
        x = alpha_s * x0 + np.sqrt(sigma_s**2 - fresh**2) * eps + fresh * rng.standard_normal(x.shape)
        trajectory.append(x)
    return schedule, np.array(trajectory)


@interactive(time=TimeControl(name="time", update_interval_ms=int(1000 / FPS)))
def clock(time=0.0):
    """One loop: show data and samples, run the sampler from pure noise, then noise the data."""
    phase = (time % PERIOD) / PERIOD
    # forward t: 0 -> 1 over [0.55, 0.9] of the loop; reverse t: 1 -> 0 over [0.1, 0.45], 0 (final samples) before
    return min(max((phase - 0.55) / 0.35, 0), 1), 0.0 if phase < 0.1 else 1 - min((phase - 0.1) / 0.35, 1)


def splat(*layers):  # (points, colour) pairs, painted in order
    img = np.ones((BINS, BINS, 3))
    for points, colour in layers:
        counts = np.histogram2d(-points[:, 1], points[:, 0], BINS, [[-EXTENT, EXTENT]] * 2)[0]
        img += (1 - np.exp(-counts / 1.5))[..., None] * (np.array(colour) - img)  # blend by point density
    img[RINGS] = (0.85, 0.1, 0.1)  # red circles of radius 3 s around the true mode centres
    return np.kron(img, np.ones((ZOOM, ZOOM, 1)))


def forward_view(data, noise, schedule, t):
    alpha, sigma = schedule_at(t, schedule)
    layout.style("forward", title=f"Forward: x_t = {alpha:.2f} x_0 + {sigma:.2f} eps   (t = {t:.2f})")
    return splat((alpha * data + sigma * noise, (0.1, 0.3, 0.8)))


def reverse_view(trajectory, data, t):
    final, reference = (np.linalg.norm(x[:, None] - MU, axis=-1).min(1).mean() for x in (trajectory[-1], data))
    steps, quality = len(trajectory) - 1, final / reference
    k = int(np.floor((1 - t) * steps + 1e-9))  # steps done once the sampler has reached time t
    # quality: mean distance of the final samples to the nearest mode, relative to the data's (1 = perfect)
    layout.style("reverse", title=f"Reverse: step {k}/{steps}. Grey: final samples, spread {quality:.2f}x data")
    # the final samples stay drawn in grey: the effect of the steps slider shows without waiting for the loop
    return splat((trajectory[-1], (0.7, 0.7, 0.7)), (trajectory[k], (0.9, 0.45, 0.0)))


def plot_schedule(schedule, trajectory, forward_t, reverse_t):
    grid, steps = np.linspace(0, 1, 501)[1:-1], np.linspace(1, 0, len(trajectory))[:-1]  # SNR is infinite at t = 0
    levels, snr = [], [(steps, 20 * np.log10(np.divide(*schedule_at(steps, schedule))), "ko", f"{schedule} steps")]
    for name, style in (("linear", "--"), ("cosine", "-")):
        alpha, sigma = schedule_at(grid, name)
        used = name == schedule  # drawn thick; only it is named in the legend: fewer entries over the curves
        levels += [[grid, alpha, dict(style=f"C0{style}", label="alpha" if used else None, linewidth=1 + 2 * used)]]
        levels += [[grid, sigma, dict(style=f"C1{style}", label="sigma" if used else None, linewidth=1 + 2 * used)]]
        snr += [[grid, 20 * np.log10(alpha / sigma), dict(style=f"k{style}", label=name, linewidth=1 + 2 * used)]]
    levels += [([forward_t] * 2, [0, 1], "b:", None), ([reverse_t] * 2, [0, 1], "r:", None)]
    layout.style("levels", title=f"thick: {schedule}, thin: the other. Dotted: current t")
    layout.style("snr", title="signal-to-noise ratio alpha/sigma, dots = the sampling steps")
    # ylim leaves room for the legend above sigma = 1
    levels = Curve(levels, xlabel="t", ylabel="level", title="Signal alpha_t, noise sigma_t", grid=True, ylim=(0, 1.4))
    snr = Curve(snr, xlabel="t", ylabel="SNR (dB)", title="structure appears near 0 dB", grid=True, ylim=(-50, 40))
    return levels, snr


@interactive_pipeline(gui=None if GIF else "auto", cache="graph", name="Diffusion with an exact score")
def diffusion():
    data, noise = dataset()
    schedule, trajectory = reverse_process()
    forward_t, reverse_t = clock()
    forward = forward_view(data, noise, schedule, forward_t)
    reverse = reverse_view(trajectory, data, reverse_t)
    levels, snr = plot_schedule(schedule, trajectory, forward_t, reverse_t)
    return [[forward, reverse], [levels, snr]]


if __name__ == "__main__":
    diffusion()  # opens the window, or runs once headless when a GIF path is given
    if GIF:
        # the first half of the loop: samples, then the sampler running from pure noise
        export_animation(diffusion, GIF, duration=PERIOD / 2, fps=FPS, output=(0, 1))
