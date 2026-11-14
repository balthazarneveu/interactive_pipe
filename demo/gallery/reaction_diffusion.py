"""Edge case: a stateful simulation (Gray-Scott reaction-diffusion) animated by a clock.

What to look at: spots, stripes or labyrinths grow from a small seed depending on feed / kill.
This is where the library is a poor fit: a pipeline is a pure function of its controls, but a
simulation is a state that evolves. Keeping the state in `context` and advancing it on every run
makes snapshots and sweeps depend on how many runs happened before. Instead the frame is made a
function of the clock: `t` seconds = `t * speed` steps from the seed, and the context only caches
the last state to resume from, so `snapshot(t=4)` is reproducible. A run advances at most 2000 steps
(the title shows the step reached), so the GUI stays responsive when the clock jumps.
"""

from typing import Annotated

import numpy as np

from interactive_pipe import TimeControl, context, interactive, interactive_pipeline, layout

N = 128


def seed():
    u, v = np.ones((N, N)), np.zeros((N, N))
    u[N // 2 - 8 : N // 2 + 8, N // 2 - 8 : N // 2 + 8], v[N // 2 - 8 : N // 2 + 8, N // 2 - 8 : N // 2 + 8] = 0.5, 0.25
    v += 0.02 * np.random.default_rng(0).random((N, N))
    return u, v


def laplacian(a):
    return np.roll(a, 1, 0) + np.roll(a, -1, 0) + np.roll(a, 1, 1) + np.roll(a, -1, 1) - 4 * a


@interactive(t=TimeControl(update_interval_ms=50))
def simulate(
    t=0.0,
    feed: Annotated[float, (0.01, 0.08), "feed"] = 0.037,
    kill: Annotated[float, (0.04, 0.07), "kill"] = 0.06,
    speed: Annotated[int, (100, 2000), "steps / second"] = 500,
):
    """A pure function of (t, feed, kill, speed): the context only caches the last state to resume from."""
    target = int(t * speed)
    state = context.get("sim")
    if state is None or state["params"] != (feed, kill) or state["step"] > target:
        state = dict(params=(feed, kill), step=0, uv=seed())  # parameters changed or time went back
    u, v = state["uv"]
    for _ in range(min(target - state["step"], 2000)):
        uvv = u * v * v
        u, v = u + 0.16 * laplacian(u) - uvv + feed * (1 - u), v + 0.08 * laplacian(v) + uvv - (feed + kill) * v
        state["step"] += 1
    state["uv"] = u, v
    context["sim"] = state
    layout.style("v", title=f"v at step {state['step']}", colormap="inferno", vmin=0, vmax=0.4, colorbar=True)
    return v


@interactive_pipeline(gui="auto")
def reaction_diffusion():
    v = simulate()
    return v


if __name__ == "__main__":
    reaction_diffusion()
