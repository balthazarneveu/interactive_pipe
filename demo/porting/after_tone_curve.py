"""Tone-curve fit with sliders (port of before_tone_curve.py).

The loop over polynomial degrees becomes a slider; compare degrees with
``tone_curve.sweep(path, degree=[1, 3, 5])``."""

from typing import Any, Dict, Tuple

import numpy as np

from interactive_pipe import Curve, interactive, interactive_pipeline


@interactive(true_gamma=(2.2, [1.0, 3.0]), noise=(0.02, [0.0, 0.1]))
def measure(exposure: np.ndarray, true_gamma: float = 2.2, noise: float = 0.02) -> np.ndarray:
    rng = np.random.default_rng(3)
    return exposure ** (1 / true_gamma) + rng.normal(0, noise, exposure.shape)


@interactive(degree=(3, [1, 7]))
def fit(exposure: np.ndarray, measured: np.ndarray, degree: int = 3) -> Dict[str, Any]:
    coefs = np.polyfit(exposure, measured, degree)
    fitted = np.polyval(coefs, exposure)
    return {"coefs": coefs, "fitted": fitted, "rmse": np.sqrt(np.mean((fitted - measured) ** 2))}


@interactive()
def plot_fit(exposure: np.ndarray, measured: np.ndarray, result: Dict[str, Any]) -> Curve:
    return Curve(
        [[exposure, measured, "k.", "measured"], [exposure, result["fitted"], "r-", f"rmse={result['rmse']:.3f}"]],
        xlabel="exposure",
    )


@interactive()
def apply_curve(result: Dict[str, Any]) -> np.ndarray:
    ramp = np.tile(np.linspace(0, 1, 256), (64, 1))
    return np.clip(np.polyval(result["coefs"], ramp), 0, 1)


@interactive_pipeline(gui="auto")
def tone_curve(exposure: np.ndarray) -> Tuple[Curve, np.ndarray]:
    measured = measure(exposure)
    result = fit(exposure, measured)
    curve = plot_fit(exposure, measured, result)
    ramp = apply_curve(result)
    return curve, ramp


if __name__ == "__main__":
    tone_curve(np.linspace(0.01, 1, 40))
