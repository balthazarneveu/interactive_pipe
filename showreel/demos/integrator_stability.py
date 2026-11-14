"""Integrator stability: a pendulum simulated three ways from the same initial condition.

    theta'' = -W0^2 sin(theta),   energy E = (1 - cos theta) + (omega / W0)^2 / 2   (units of m g L)

Explicit Euler updates angle and velocity from the old state: each step pushes the bob slightly
outwards: the energy grows at every swing (the bob rises above its starting height, the grey line)
until, with a larger step or angle, the pendulum goes over the top.
Symplectic (semi-implicit) Euler updates the velocity first and uses the new velocity for the angle:
same cost, but the energy only wobbles around the true value. RK4 costs four force evaluations per
step and its energy drifts (slowly downwards) only when the step gets large.

    python integrator_stability.py             # interactive window (press v to export a GIF)
    python integrator_stability.py out.gif     # no window: render the animated pendulums to a GIF
"""

import sys

import numpy as np

from interactive_pipe import Curve, TimeControl, export_animation, interactive, interactive_pipeline, layout

W0, DURATION, FPS = np.pi, 10.0, 25  # small-angle period 2 s
NAMES = ("explicit Euler", "symplectic Euler", "RK4")
COLOURS = np.array([[31, 119, 180], [255, 127, 14], [44, 160, 44]]) / 255  # matplotlib C0, C1, C2
H, PANEL, ROD = 240, 240, 90  # image height, width of each pendulum panel, rod length (pixels)
Y, X = np.mgrid[:H, :PANEL] - np.array([H / 2, PANEL / 2])[:, None, None]  # pixel coordinates around the pivot
GIF = next((arg for arg in sys.argv[1:] if arg.endswith(".gif")), None)


def force(y):  # y = (theta, omega) -> dy/dt
    return np.array([y[1], -(W0**2) * np.sin(y[0])])


def explicit_euler(y, h):
    return y + h * force(y)


def symplectic_euler(y, h):
    omega = y[1] - h * W0**2 * np.sin(y[0])
    return np.array([y[0] + h * omega, omega])


def rk4(y, h):
    k1 = force(y)
    k2 = force(y + h / 2 * k1)
    k3 = force(y + h / 2 * k2)
    k4 = force(y + h * k3)
    return y + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)


def energy(states):  # (..., 2) -> (...)
    return 1 - np.cos(states[..., 0]) + 0.5 * (states[..., 1] / W0) ** 2


@interactive(time_step=(0.02, [0.005, 0.2], "time step (s)"), angle=(60.0, [5.0, 170.0], "initial angle (deg)"))
def simulate(time_step=0.02, angle=60.0):
    """The whole run, once per parameter change: (integrator, step, (theta, omega))."""
    t = np.arange(0, DURATION + time_step, time_step)
    states = np.zeros((3, len(t), 2))
    states[:, 0] = np.deg2rad(angle), 0.0
    for k, step in enumerate((explicit_euler, symplectic_euler, rk4)):
        for i in range(1, len(t)):
            states[k, i] = step(states[k, i - 1], time_step)
    return t, states


@interactive(time=TimeControl(name="time", update_interval_ms=1000 // FPS))
def clock(t, time=0.0):
    return np.searchsorted(t, time % DURATION)  # the animation loops over the run


def draw_pendulums(t, states, now):
    """Side by side, colour-coded. Grey line: the starting height, which a conserved energy never lets the bob pass."""
    panels = []
    for k, (theta, _) in enumerate(states[:, now]):
        panel = np.ones((H, PANEL, 3))
        panel[np.abs(np.hypot(X, Y) - ROD) < 0.8] = 0.9  # the circle the bob lives on
        panel[(np.abs(Y - ROD * np.cos(states[k, 0, 0])) < 1) & (np.abs(X) < PANEL / 2 - 10)] = 0.6
        bob_x, bob_y = ROD * np.sin(theta), ROD * np.cos(theta)
        along = np.clip((X * bob_x + Y * bob_y) / ROD**2, 0, 1)  # closest point of the rod, as a fraction
        panel[np.hypot(X - along * bob_x, Y - along * bob_y) < 2] = 0.2
        panel[np.hypot(X - bob_x, Y - bob_y) < 12] = COLOURS[k]
        panels.append(panel)
    layout.style("pendulums", title=f"t = {t[now]:.2f} s: {' | '.join(NAMES)}")
    return np.hstack(panels)


def phase_portrait(states, now):
    theta0 = states[0, 0, 0]
    theta = np.linspace(-theta0, theta0, 200)
    omega = W0 * np.sqrt(np.maximum(2 * (np.cos(theta) - np.cos(theta0)), 0))
    exact = (np.r_[theta, theta[::-1]], np.r_[omega, -omega], {"style": "k--", "linewidth": 1})
    wrapped = (states[..., 0] + np.pi) % (2 * np.pi) - np.pi  # a pendulum going over the top re-enters at -pi
    broken = np.where(np.abs(np.diff(wrapped, prepend=wrapped[:, :1])) > np.pi, np.nan, wrapped)
    paths = [(broken[k], states[k, :, 1], f"C{k}-") for k in range(3)]
    dots = [([wrapped[k, now]], [states[k, now, 1]], f"C{k}o") for k in range(3)]
    title = "Phase portrait (dashed: exact orbit)"
    axes = dict(xlim=(-np.pi, np.pi), ylim=(-2.2 * W0, 2.2 * W0), grid=True)
    return Curve([*paths, exact, *dots], xlabel="angle (rad)", ylabel="angular velocity (rad/s)", title=title, **axes)


def plot_energy(t, states, now):
    e = energy(states) / energy(states[0, 0])
    curves = [(t, e[k], f"C{k}-") for k in range(3)] + [([t[now]] * 2, [0, 5], "k:")]
    title = "Energy / initial: Euler {:.2f}, symplectic {:.3f}, RK4 {:.4f}".format(*e[:, now])
    return Curve(curves, xlabel="time (s)", ylabel="relative energy", title=title, grid=True, ylim=(0.8, 4.0))


@interactive_pipeline(gui=None if GIF else "auto", cache="graph", name="Integrator stability")
def integrator_stability():
    t, states = simulate()
    now = clock(t)
    pendulums = draw_pendulums(t, states, now)
    phase = phase_portrait(states, now)
    energy_curve = plot_energy(t, states, now)
    return [[pendulums], [phase, energy_curve]]


if __name__ == "__main__":
    integrator_stability()  # opens the window, or runs once headless when a GIF path is given
    if GIF:
        export_animation(integrator_stability, GIF, duration=DURATION, fps=FPS / 2, output=(0, 0))
