"""Tracking: two Kalman filters (constant velocity, constant acceleration) on a noisy 2D path.

What to look at: the target turns sharply at t = 4 s. With a small process noise q the
constant-velocity filter is smooth but overshoots the turn, and its normalised innovation (the
surprise of each new measurement, ~1 when the filter is consistent) jumps far above 1 there; a
large q (1e4) follows the turn but lets the measurement noise through; q = 100 is the best compromise
here (see the RMS table). The constant-acceleration model handles the turn with a smaller q. The
same q and r sliders drive both filters: one slider each, on a log scale.
"""

from typing import Any, List, Tuple

import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from interactive_pipe import Control, Curve, Table, interactive, interactive_pipeline

DT, N = 0.05, 200
Q = Control(1.0, [1e-2, 1e5], scale="log", name="process noise q")
R = Control(1.0, [1e-2, 1e2], scale="log", name="measurement noise r")


def make_track(sigma: float = 1.0, seed: int = 2) -> Tuple[np.ndarray, np.ndarray]:
    """True positions (N, 2) and noisy measurements: straight, a sharp turn at t = 4 s, straight."""
    t = np.arange(N) * DT
    heading = np.where(t < 4, 0.0, np.minimum(t - 4, 0.5) * np.pi)  # 90 degrees in 0.5 s
    velocity = 5 * np.stack([np.cos(heading), np.sin(heading)], axis=-1)
    truth = np.cumsum(velocity * DT, axis=0)
    return truth, truth + sigma * np.random.default_rng(seed).standard_normal(truth.shape)


def kalman(measurements: np.ndarray, q: float, r: float, order: int) -> Tuple[np.ndarray, np.ndarray]:
    """Per-axis polynomial model of `order` (1 = velocity, 2 = acceleration). Returns estimates, NIS."""
    n = order + 1
    F = np.array(
        [[DT ** max(j - i, 0) / np.prod(range(1, j - i + 1)) if j >= i else 0 for j in range(n)] for i in range(n)]
    )
    G = np.array([DT ** (n - k) / np.prod(range(1, n - k + 1)) for k in range(n)])[:, None]
    Qm, H = q * G @ G.T, np.eye(1, n)
    x, P = np.zeros((n, 2)), np.eye(n) * 100.0
    x[0] = measurements[0]
    estimates, nis = [], []
    for z in measurements:
        x, P = F @ x, F @ P @ F.T + Qm
        S = (H @ P @ H.T).item() + r
        innovation = z - (H @ x)[0]
        K = P @ H.T / S
        x, P = x + K @ innovation[None], (np.eye(n) - K @ H) @ P
        estimates.append(x[0].copy())
        nis.append(innovation @ innovation / S / 2)  # normalised innovation squared, per axis
    return np.array(estimates), np.array(nis)


@interactive(q=Q, r=R)
def constant_velocity(measurements: np.ndarray, q: float = 1.0, r: float = 1.0) -> Tuple[np.ndarray, np.ndarray]:
    return kalman(measurements, q, r, order=1)


@interactive(q=Q, r=R)
def constant_acceleration(measurements: np.ndarray, q: float = 1.0, r: float = 1.0) -> Tuple[np.ndarray, np.ndarray]:
    return kalman(measurements, q, r, order=2)


@interactive
def compare(
    truth: np.ndarray, measurements: np.ndarray, cv: np.ndarray, cv_nis: np.ndarray, ca: np.ndarray, ca_nis: np.ndarray
) -> Tuple[Axes, Curve, Table]:
    ax = Figure(figsize=(5, 4)).subplots()
    ax.plot(*measurements.T, "k.", markersize=2, label="measurements")
    ax.plot(*truth.T, "k-", linewidth=1, label="truth")
    ax.plot(*cv.T, "r-", label="constant velocity")
    ax.plot(*ca.T, "b-", label="constant acceleration")
    ax.legend(loc="upper left", fontsize=8)
    t = np.arange(N) * DT
    innovation = Curve(
        [
            [t, cv_nis, "r-", "constant velocity"],
            [t, ca_nis, "b-", "constant acceleration"],
            [t, np.ones(N), "k--", "consistent"],
        ],
        xlabel="time (s)",
        title="normalised innovation",
    )
    rms = {"model": ["constant velocity", "constant acceleration", "measurements"]}
    rms["RMS error"] = [f"{np.sqrt(np.mean((est - truth) ** 2)):.2f}" for est in (cv, ca, measurements)]
    rms["mean NIS"] = [f"{cv_nis.mean():.2f}", f"{ca_nis.mean():.2f}", "-"]
    return ax, innovation, Table(rms)


@interactive_pipeline(gui="auto")
def g2_kalman_tracking(truth: np.ndarray, measurements: np.ndarray) -> List[List[Any]]:
    cv, cv_nis = constant_velocity(measurements)
    ca, ca_nis = constant_acceleration(measurements)
    trajectory, innovation, errors = compare(truth, measurements, cv, cv_nis, ca, ca_nis)
    return [[trajectory, innovation, errors]]


if __name__ == "__main__":
    g2_kalman_tracking(*make_track())
