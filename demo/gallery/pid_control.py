"""Control engineering: PID control of a lightly damped second-order plant.

What to look at: with P only the response settles with a static error and rings; I removes the
error but adds overshoot; D damps the ringing. Watch the command: a large Kd gives a kick at the
step, and the actuator saturation (u_max) slows everything down and causes integral wind-up.
The open-loop Bode plot shows the gain crossover and the phase margin: a small margin = ringing.
"""

from typing import Annotated

import numpy as np
from matplotlib.figure import Figure

from interactive_pipe import Control, Curve, interactive, interactive_pipeline

WN, ZETA = 2 * np.pi * 1.0, 0.15  # plant: natural frequency 1 Hz, damping 0.15
DT, T_END, TAU_D = 1e-3, 6.0, 0.01  # time step, duration, derivative filter time constant (s)
# named controls in an alias: one slider each, shared by simulate() and bode()
Kp = Annotated[float, Control(2.0, [0.0, 10.0], name="Kp")]
Ki = Annotated[float, Control(3.0, [0.0, 20.0], name="Ki")]
Kd = Annotated[float, Control(0.15, [0.0, 1.0], name="Kd")]


@interactive
def simulate(kp: Kp = 2.0, ki: Ki = 3.0, kd: Kd = 0.15, u_max: Annotated[float, (0.5, 20.0), "u_max"] = 20.0):
    t = np.arange(0, T_END, DT)
    ref = (t >= 0.5).astype(float)
    y = dy = integral = d_filt = prev_err = 0.0
    out, cmd = np.zeros_like(t), np.zeros_like(t)
    for i, r in enumerate(ref):
        err = r - y
        d_filt += (DT / TAU_D) * ((err - prev_err) / DT - d_filt)
        u = kp * err + ki * integral + kd * d_filt
        u_sat = np.clip(u, -u_max, u_max)
        integral += err * DT
        prev_err = err
        dy += DT * (WN**2 * (u_sat - y) - 2 * ZETA * WN * dy)
        y += DT * dy
        out[i], cmd[i] = y, u_sat
    response = Curve(
        [[t, ref, "k--", "reference"], [t, out, "b-", "output"]], xlabel="time (s)", ylim=(-0.2, 2.0), grid=True
    )
    command = Curve([[t, cmd, "r-", "command u"]], xlabel="time (s)", grid=True)
    return response, command


@interactive
def bode(kp: Kp = 2.0, ki: Ki = 3.0, kd: Kd = 0.15):
    w = np.logspace(-1, 3, 800)
    s = 1j * w
    loop = (kp + ki / s + kd * s / (1 + TAU_D * s)) * WN**2 / (s**2 + 2 * ZETA * WN * s + WN**2)
    mag, phase = 20 * np.log10(np.abs(loop)), np.degrees(np.unwrap(np.angle(loop)))
    fig = Figure(figsize=(4.5, 4))
    ax_mag, ax_phase = fig.subplots(2, 1, sharex=True)
    ax_mag.semilogx(w / (2 * np.pi), mag)
    ax_mag.axhline(0, color="gray", linewidth=0.8)
    ax_phase.semilogx(w / (2 * np.pi), phase)
    ax_phase.axhline(-180, color="gray", linewidth=0.8)
    cross = np.nonzero(np.diff(np.sign(mag)) < 0)[0]
    if len(cross):
        fc, margin = w[cross[-1]] / (2 * np.pi), 180 + phase[cross[-1]]
        for ax in (ax_mag, ax_phase):
            ax.axvline(fc, color="tab:orange", linestyle=":")
        ax_mag.set_title(f"crossover {fc:.2f} Hz, margin {margin:.0f} deg")
    ax_mag.set_ylabel("gain (dB)")
    ax_phase.set(ylabel="phase (deg)", xlabel="frequency (Hz)")
    fig.tight_layout()
    return fig


@interactive_pipeline(gui="auto")
def pid_control():
    response, command = simulate()
    open_loop = bode()
    return [[response, open_loop], [command]]


if __name__ == "__main__":
    pid_control()
