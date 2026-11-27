"""Edge case: a stateful simulation (Gray-Scott reaction-diffusion) animated by a clock.

What to look at: spots, stripes or labyrinths grow from a small seed depending on feed / kill.
The state lives in `context` and each run advances it to the clock: `t` seconds = `t * speed` steps
from the seed (moving feed / kill continues the simulation with the new values). Snapshots and sweeps
start each picture from an empty context, so `snapshot(t=4)` is reproducible. A run advances at most
2000 steps (the title shows the step reached), so the GUI stays responsive when the clock jumps.
"""

from typing import Annotated, Any, Dict, Optional, Tuple

import numpy as np

from interactive_pipe import TimeControl, context, interactive, interactive_pipeline, layout

N = 128


def seed() -> Tuple[np.ndarray, np.ndarray]:
    u, v = np.ones((N, N)), np.zeros((N, N))
    u[N // 2 - 8 : N // 2 + 8, N // 2 - 8 : N // 2 + 8], v[N // 2 - 8 : N // 2 + 8, N // 2 - 8 : N // 2 + 8] = 0.5, 0.25
    v += 0.02 * np.random.default_rng(0).random((N, N))
    return u, v


def laplacian(a: np.ndarray) -> np.ndarray:
    lap: np.ndarray = np.roll(a, 1, 0) + np.roll(a, -1, 0) + np.roll(a, 1, 1) + np.roll(a, -1, 1) - 4 * a
    return lap


@interactive(t=TimeControl(update_interval_ms=50))
def simulate(
    t: float = 0.0,
    feed: Annotated[float, (0.01, 0.08), "feed"] = 0.037,
    kill: Annotated[float, (0.04, 0.07), "kill"] = 0.06,
    speed: Annotated[int, (100, 2000), "steps / second"] = 500,
) -> np.ndarray:
    """Advance the state kept in the context up to the clock."""
    target = int(t * speed)
    state: Optional[Dict[str, Any]] = context.get("sim")
    if state is None or state["step"] > target:  # first run, or the clock went back
        state = dict(step=0, uv=seed())
    u: np.ndarray
    v: np.ndarray
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
def reaction_diffusion() -> np.ndarray:
    v = simulate()
    return v


if __name__ == "__main__":
    reaction_diffusion()
