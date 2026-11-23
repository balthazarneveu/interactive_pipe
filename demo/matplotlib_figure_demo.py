"""
Demo: any matplotlib figure as a pipeline output.

Two point charges; the sliders move them apart and change the second charge.
- "field": a matplotlib Figure (equipotential contours + electric field
  arrows) — something a Curve cannot draw.
- "potential": the same potential as a raw 2D array, shown as a diverging
  heatmap with a colorbar (layout.style colormap / center / colorbar).

A filter returns the Figure (or an Axes); interactive_pipe rasterises it for
every backend and for snapshots. Build it with matplotlib.figure.Figure()
rather than pyplot: no global state, nothing to close.
"""

import argparse
from typing import List, Union

import numpy as np
from matplotlib.figure import Figure

from interactive_pipe import interactive, interactive_pipeline, layout

GRID = 160


@interactive(
    separation=(1.0, [0.2, 2.0]),
    charge_ratio=(-1.0, [-2.0, 2.0]),
)
def compute_potential(separation: float = 1.0, charge_ratio: float = -1.0) -> np.ndarray:
    """Electric potential of +1 at (-d/2, 0) and `charge_ratio` at (+d/2, 0)."""
    y, x = np.mgrid[-2.0 : 2.0 : GRID * 1j, -2.0 : 2.0 : GRID * 1j]
    softening = 0.05  # keeps the potential finite on the charges
    r1 = np.hypot(x + separation / 2.0, y) + softening
    r2 = np.hypot(x - separation / 2.0, y) + softening
    potential = 1.0 / r1 + charge_ratio / r2
    layout.style("potential", title="Potential (heatmap)", colormap="RdBu_r", center=0.0, colorbar=True, unit="V")
    return np.clip(potential, -5.0, 5.0)


@interactive()
def plot_field(potential: np.ndarray) -> Figure:
    """Equipotentials and field arrows of the potential map."""
    ey, ex = np.gradient(-potential)
    fig = Figure(figsize=(5.0, 4.5), layout="constrained")
    ax = fig.subplots()
    extent = (-2.0, 2.0, -2.0, 2.0)
    levels = np.linspace(-3.0, 3.0, 13)
    contours = ax.contour(potential, levels=levels, extent=extent, cmap="RdBu_r", linewidths=1.0)
    ax.clabel(contours, fontsize=7, fmt="%.1f")
    step = 10
    y, x = np.mgrid[-2.0 : 2.0 : GRID * 1j, -2.0 : 2.0 : GRID * 1j]
    norm = np.hypot(ex, ey) + 1e-9
    ax.quiver(
        x[::step, ::step],
        y[::step, ::step],
        (ex / norm)[::step, ::step],
        (ey / norm)[::step, ::step],
        np.log(norm[::step, ::step]),
        cmap="viridis",
        scale=30,
    )
    ax.set_aspect("equal")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_title("Equipotentials and field direction")
    layout.style("field", title="Field (matplotlib Figure)")
    return fig


def field_pipeline() -> List[Union[Figure, np.ndarray]]:
    potential = compute_potential()
    field = plot_field(potential)
    return [field, potential]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="matplotlib figure output demo")
    parser.add_argument(
        "-b",
        "--backend",
        type=str,
        choices=["qt", "dpg", "gradio", "mpl", "nb"],
        default="qt",
        help="Backend to use (default: qt)",
    )
    args = parser.parse_args()
    interactive_pipeline(gui=args.backend, cache=True, name="matplotlib figure demo")(field_pipeline)()
