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
SIZE, ROD = 320, 110  # pendulum image and rod length (pixels)
Y, X = np.mgrid[:SIZE, :SIZE] - SIZE / 2  # pixel coordinates around the pivot
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
    return y + h / 6 * (k1 + 2 * k2 + 2 * k3 + force(y + h * k3))  # the last term is k4


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
    """One pivot, three bobs (largest underneath). Grey line: the starting height, which a conserved energy never
    lets the bob pass. Arcs outside the circle: every angle each bob reaches during the whole run."""
    img = np.ones((SIZE, SIZE, 3))
    img[np.abs(np.hypot(X, Y) - ROD) < 0.8] = 0.85  # the circle the bobs live on
    img[np.abs(Y - ROD * np.cos(states[0, 0, 0])) < 1] = 0.6
    for k, (theta, _) in enumerate(states[:, now]):
        reached = (np.arctan2(X, Y) - states[k, :, 0].min()) % (2 * np.pi) <= np.ptp(states[k, :, 0])
        img[reached & (np.abs(np.hypot(X, Y) - ROD - 14 - 9 * k) < 3)] = 0.4 + 0.6 * COLOURS[k]  # faint
        bob_x, bob_y = ROD * np.sin(theta), ROD * np.cos(theta)
        along = np.clip((X * bob_x + Y * bob_y) / ROD**2, 0, 1)  # closest point of the rod, as a fraction
        img[np.hypot(X - along * bob_x, Y - along * bob_y) < 1.5] = 0.2
        img[np.hypot(X - bob_x, Y - bob_y) < 14 - 4 * k] = COLOURS[k]
    layout.style("pendulums", title=f"Pendulums at t = {t[now]:.2f} s (arcs: whole run)")
    return img


def phase_portrait(states, now):
    theta = np.linspace(-1, 1, 200) * states[0, 0, 0]  # the exact orbit through the initial angle
    omega = W0 * np.sqrt(np.maximum(2 * (np.cos(theta) - np.cos(theta[-1])), 0))
    exact = (np.r_[theta, theta[::-1]], np.r_[omega, -omega], {"style": "k--", "linewidth": 1})
    wrapped = (states[..., 0] + np.pi) % (2 * np.pi) - np.pi  # a pendulum going over the top re-enters at -pi
    broken = np.where(np.abs(np.diff(wrapped, prepend=wrapped[:, :1])) > np.pi, np.nan, wrapped)
    paths = [(broken[k], states[k, :, 1], f"C{k}-") for k in range(3)]
    dots = [([wrapped[k, now]], [states[k, now, 1]], f"C{k}o") for k in range(3)]
    layout.style("phase", title="Phase portrait (dashed: exact orbit)")
    axes = dict(xlim=(-np.pi, np.pi), ylim=(-2.2 * W0, 2.2 * W0), grid=True)
    return Curve([*paths, exact, *dots], xlabel="angle (rad)", ylabel="angular velocity (rad/s)", **axes)


def plot_energy(t, states, now):
    e = energy(states) / energy(states[0, 0])
    ylim = (0.8, 4.6)  # fixed axis: no rescaling while a slider moves; clipped curves ride its edges
    curves = [(t, np.clip(e[k], *ylim), f"C{k}-", NAMES[k]) for k in range(3)] + [([t[now]] * 2, ylim, "k:")]
    # the title gives the true (unclipped) values
    layout.style("energy_curve", title="E / E0: Euler {:.2f}, symplectic {:.3f}, RK4 {:.4f}".format(*e[:, now]))
    return Curve(curves, xlabel="time (s)", ylabel="relative energy (clipped)", grid=True, ylim=ylim)


@interactive_pipeline(gui=None if GIF else "auto", cache="graph", name="Integrator stability")
def integrator_stability():
    t, states = simulate()
    now = clock(t)
    pendulums = draw_pendulums(t, states, now)
    phase = phase_portrait(states, now)
    energy_curve = plot_energy(t, states, now)
    return [pendulums, phase, energy_curve]


if __name__ == "__main__":
    integrator_stability()  # opens the window, or runs once headless when a GIF path is given
    if GIF:
        export_animation(integrator_stability, GIF, duration=DURATION, fps=FPS / 2, output=(0, 0))
