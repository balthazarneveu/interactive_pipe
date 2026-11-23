"""Machine learning: inspect the loss curves of a learning-rate sweep (synthetic runs).

What to look at: raw curves are too noisy to rank the runs (with no smoothing, the last value names
lr 0.01 the best by luck); an exponential moving average (0.9) makes it clear that lr 0.03 wins.
A log scale shows that the lr 0.3 run diverges and the lr 0.001 run is still improving. The "best
run" readout and the summary table follow the chosen metric. Raise the selection threshold until
no run passes it: the plot and the table say so instead of failing.
"""

from typing import Annotated, Literal

import numpy as np

from interactive_pipe import Curve, SingleCurve, Table, interactive, interactive_pipeline, layout

STEPS = np.arange(1, 501)


def make_runs(seed=3):
    """{run name: {metric: values}} for a learning-rate sweep."""
    rng = np.random.default_rng(seed)
    runs = {}
    for lr, floor in ((0.001, 0.30), (0.01, 0.12), (0.03, 0.08), (0.1, 0.15), (0.3, None)):
        if floor is None:  # too large: diverges after a while
            train = 2.0 * np.exp(-STEPS / 50) + 0.4 + np.maximum(STEPS - 200, 0) ** 2 / 2e4
        else:
            train = 2.0 * np.exp(-lr * STEPS / 0.5) + floor
        val = train * 1.1 + 0.02 * STEPS / 500
        noisy = {
            "train loss": train * np.exp(0.3 * rng.standard_normal(STEPS.size)),
            "val loss": val * np.exp(0.3 * rng.standard_normal(STEPS.size)),
        }
        noisy["val accuracy"] = 1 / (1 + noisy["val loss"])
        runs[f"lr {lr}"] = noisy
    return runs


def ema(values, smoothing):
    out, acc = np.empty_like(values), values[0]
    for i, v in enumerate(values):
        acc = smoothing * acc + (1 - smoothing) * v
        out[i] = acc
    return out


@interactive
def inspect_runs(
    runs,
    metric: Literal["train loss", "val loss", "val accuracy"] = "val loss",
    smoothing: Annotated[float, (0.0, 0.99), "smoothing"] = 0.9,
    log_scale: Annotated[bool, "log scale"] = True,
    threshold: Annotated[float, (0.0, 1.0), "show runs with final val accuracy above"] = 0.0,
):
    selected = {name: m for name, m in runs.items() if m["val accuracy"][-20:].mean() > threshold}
    lower_is_better = metric != "val accuracy"
    lines = [SingleCurve(x=STEPS, y=ema(m[metric], smoothing), label=name) for name, m in selected.items()]
    curves = Curve(lines, xlabel="step", ylabel=metric, grid=True, yscale="log" if log_scale else None)
    final = {name: float(ema(m[metric], smoothing)[-1]) for name, m in selected.items()}
    best = (min if lower_is_better else max)(final, key=lambda name: final[name]) if final else None
    layout.style("curves", title=f"best: {best} ({final[best]:.3f})" if best else "no run above the threshold")
    rows = [
        {"run": name, f"final {metric}": f"{value:.3f}", "best": "*" if name == best else ""}
        for name, value in final.items()
    ]
    return curves, Table(rows, title=f"{len(rows)} of {len(runs)} runs")


@interactive_pipeline(gui="auto")
def g2_training_curves(runs):
    curves, summary = inspect_runs(runs)
    return curves, summary


if __name__ == "__main__":
    g2_training_curves(make_runs())
