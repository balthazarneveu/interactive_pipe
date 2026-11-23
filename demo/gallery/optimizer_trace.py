"""Optimisation trace: gradient descent variants on the Rosenbrock valley.

What to look at: plain gradient descent zig-zags across the narrow curved valley and crawls along
its floor; momentum and Nesterov overshoot then accelerate along it; Adam normalises the step per
axis. Raise the learning rate until the trajectory diverges (the loss curve shoots up), and compare
how many steps each method needs to reach the minimum at (1, 1).
"""

from typing import Annotated, Literal, Tuple

import numpy as np
from matplotlib.figure import Figure

from interactive_pipe import Curve, interactive, interactive_pipeline

X, Y = np.meshgrid(np.linspace(-2, 2, 200), np.linspace(-1, 3, 200))


def loss(p: np.ndarray) -> np.ndarray:
    value: np.ndarray = (1 - p[..., 0]) ** 2 + 10 * (p[..., 1] - p[..., 0] ** 2) ** 2
    return value


def grad(p: np.ndarray) -> np.ndarray:
    x, y = p
    return np.array([-2 * (1 - x) - 40 * x * (y - x**2), 20 * (y - x**2)])


@interactive
def optimize(
    optimizer: Literal["gd", "momentum", "nesterov", "adam"] = "momentum",
    lr: Annotated[float, (1e-4, 0.3, "log"), "learning rate"] = 0.01,
    momentum: Annotated[float, (0.0, 0.99), "Momentum / beta1"] = 0.9,
    steps: Annotated[int, (1, 500), "Steps"] = 150,
) -> np.ndarray:
    p, v, s = np.array([-1.5, 2.5]), np.zeros(2), np.zeros(2)
    path = [p]
    for k in range(1, steps + 1):
        if optimizer == "gd":
            p = p - lr * grad(p)
        elif optimizer in ("momentum", "nesterov"):
            g = grad(p - lr * momentum * v) if optimizer == "nesterov" else grad(p)
            v = momentum * v + g
            p = p - lr * v
        else:  # adam
            g = grad(p)
            v, s = momentum * v + (1 - momentum) * g, 0.999 * s + 0.001 * g**2
            p = p - 10 * lr * (v / (1 - momentum**k)) / (np.sqrt(s / (1 - 0.999**k)) + 1e-8)
        if np.abs(p).max() > 1e3:  # diverged: stop before overflowing
            break
        path.append(p)
    return np.array(path)


@interactive()
def contour(path: np.ndarray) -> Figure:
    fig = Figure()
    ax = fig.subplots()
    ax.contour(X, Y, np.log10(loss(np.stack([X, Y], axis=-1)) + 1e-3), levels=20, cmap="viridis")
    ax.plot(path[:, 0], path[:, 1], "r.-", markersize=3, linewidth=1)
    ax.plot(1, 1, "k*", markersize=12)
    ax.set(xlim=(-2, 2), ylim=(-1, 3), xlabel="x", ylabel="y", title=f"end at ({path[-1, 0]:.2f}, {path[-1, 1]:.2f})")
    return fig


@interactive()
def loss_curve(path: np.ndarray) -> Curve:
    return Curve([[np.arange(len(path)), np.log10(loss(path) + 1e-12), "b-", "log10 loss"]], xlabel="step", grid=True)


@interactive_pipeline(gui="auto")
def optimizer_trace() -> Tuple[Figure, Curve]:
    path = optimize()
    trajectory = contour(path)
    losses = loss_curve(path)
    return trajectory, losses


if __name__ == "__main__":
    optimizer_trace()
