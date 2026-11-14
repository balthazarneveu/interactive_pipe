"""Numerical simulation: explicit finite differences for the 2D heat equation, stepped by a slider.

What to look at: heat spreads from the hot bar into the plate; with cold edges (Dirichlet) the
plate cools down towards 0, with insulated edges (Neumann) the mean temperature stays constant
(see the title). The scheme is stable only for r = D dt / dx^2 <= 0.25: above it, a checkerboard
grows from the hot bar and the field explodes within a few hundred steps.
The state is cached in `context` keyed on the parameters, so moving the step slider forward only
computes the new steps; every frame is still a function of the controls (snapshots reproducible).
"""

from typing import Annotated, Literal

import numpy as np

from interactive_pipe import Curve, context, interactive, interactive_pipeline, layout

N = 64


def initial_plate():
    plate = np.zeros((N, N))
    plate[20:44, 30:34] = 100.0  # hot bar, degrees
    return plate


def step_once(u, r, edges):
    padded = np.pad(u, 1, mode="edge" if edges == "insulated" else "constant")
    laplacian = padded[:-2, 1:-1] + padded[2:, 1:-1] + padded[1:-1, :-2] + padded[1:-1, 2:] - 4 * u
    return u + r * laplacian


@interactive
def simulate(
    plate,
    step: Annotated[int, (0, 2000), "time step"] = 300,
    r: Annotated[float, (0.05, 0.3), "r = D dt / dx^2"] = 0.2,
    edges: Literal["cold", "insulated"] = "cold",
):
    key = (r, edges, plate.tobytes())
    cached = context.get("heat")  # (key, step, field) of the last run, if it was the same simulation
    if cached is not None and cached[0] == key and cached[1] <= step:
        done, u = cached[1], cached[2]
    else:
        done, u = 0, plate.astype(float)
    with np.errstate(over="ignore", invalid="ignore"):
        for _ in range(step - done):
            u = step_once(u, r, edges)
    context["heat"] = (key, step, u)
    title = f"step {step}: mean {np.mean(u):.3g}, max {np.max(u):.3g} deg C"
    layout.style("temperature", title=title, colormap="inferno", vmin=0, vmax=20, colorbar=True, unit="deg C")
    return u


@interactive
def profile(temperature):
    middle = Curve([[np.arange(N), temperature[N // 2], "r-", "row 32"]], xlabel="x (cells)", ylabel="deg C")
    return middle


@interactive_pipeline(gui="auto")
def g2_heat_diffusion(plate):
    temperature = simulate(plate)
    cross_section = profile(temperature)
    return temperature, cross_section


if __name__ == "__main__":
    g2_heat_diffusion(initial_plate())
