"""Can an output be displayed, and will it look like what the filter meant?

The GUI backends and the snapshot renderer accept a fixed set of output types.
Anything else is drawn as a placeholder (or makes a backend raise), and some
arrays are displayed misleadingly (a uint8 image clipped to [0, 1] is white,
NaN is black). ``output_problems`` names these cases with the fix; ``snapshot``
and ``sweep`` log them, so an agent looking at the PNG knows why a cell is
empty or saturated. Detection only: no output is converted here.
"""

import logging
from typing import Any, Iterable, List, Optional, Tuple

import numpy as np

SUPPORTED_OUTPUTS = (
    "numpy images (H, W) or (H, W, 3) - float in [0, 1] -, 1D numpy arrays (drawn as curves), "
    "Curve, SingleCurve, Table, str, and None (empty cell)"
)

#: (severity, problem, fix) - severity is "unsupported" (drawn nowhere), "gui" (snapshot draws it,
#: some GUI backends crash on it or show it wrong) or "misleading" (drawn wrong everywhere)
Problem = Tuple[str, str, str]


def _known_object(value: Any) -> bool:
    try:
        from interactive_pipe.data_objects.curves import Curve, SingleCurve
        from interactive_pipe.data_objects.table import Table
    except ImportError:  # pragma: no cover - optional dependencies
        return False
    return isinstance(value, (Curve, SingleCurve, Table))


def _object_fix(value: Any) -> str:
    module = type(value).__module__.split(".")[0]
    name = type(value).__name__
    if module == "torch":
        return "convert it in the filter: `return tensor.detach().cpu().numpy()` (channels last, (H, W, 3))"
    if module == "PIL":
        return "convert it in the filter: `return np.asarray(pil_image) / 255.0`"
    if module == "matplotlib":
        return "return the data (numpy array, Curve) instead of a matplotlib object"
    if isinstance(value, dict):
        return "return the arrays as separate outputs (`return a, b`), or a Table for tabular data"
    if isinstance(value, (list, tuple)):
        return "return the elements as separate outputs (`return a, b`), unpacked in the pipeline (`a, b = f(x)`)"
    if isinstance(value, (bool, int, float, complex, np.generic)):
        return "display it as text (`return f'{value:.3f}'`) or as a curve / image"
    return f"convert the {name} to a numpy array, a Curve or a Table in the filter"


HEATMAP_STYLE_KEYS = ("colormap", "vmin", "vmax")


def array_problem(value: np.ndarray, style: Optional[dict] = None) -> Optional[Problem]:
    """Display problem of a numpy array, None when it is displayed faithfully.

    ``style``: the output's ``layout.style`` options; a heatmap style
    (colormap / vmin / vmax) maps any value range itself.
    """
    shape = value.shape
    if value.size == 0:
        return ("unsupported", f"empty array {shape}", "return a non-empty array (or None for an empty cell)")
    if value.dtype.kind in "cOSUVMm":
        return (
            "unsupported",
            f"{value.dtype} array cannot be displayed as an image",
            "convert to float (e.g. np.abs(z) for complex values)",
        )
    if value.ndim == 0 or value.ndim > 3:
        fix = "select one image (e.g. batch[0])" if value.ndim > 3 else "return a 1D, 2D or 3D array"
        return ("unsupported", f"{value.ndim}D array {shape}", fix)
    if value.ndim == 3:
        channels = shape[-1]
        if channels != 3:
            if shape[0] in (1, 3, 4) and channels > 4:
                return (
                    "unsupported",
                    f"channel-first array {shape}",
                    "move the channels last: np.moveaxis(img, 0, -1) (and img[..., 0] for one channel)",
                )
            if channels == 1:
                return (
                    "gui",
                    f"single-channel array {shape} (the Qt and Dear PyGui backends raise on it)",
                    "drop the channel axis: img[..., 0]",
                )
            if channels == 4:
                return (
                    "gui",
                    f"RGBA array {shape} (the Qt backend raises on it)",
                    "drop the alpha channel: img[..., :3]",
                )
            return ("unsupported", f"{channels}-channel array {shape}", "return (H, W) or (H, W, 3)")
    if value.ndim == 1:
        return None  # drawn as a curve
    if value.dtype.kind in "ui":
        return (
            "gui",
            f"{value.dtype} image: the GUI backends expect floats in [0, 1] and clip, it shows almost white there",
            "scale it: img / 255.0 (uint8) or img / 65535.0 (uint16)",
        )
    heatmap = value.ndim == 2 and bool(style) and any(style.get(key) is not None for key in HEATMAP_STYLE_KEYS)
    if value.dtype.kind == "f" and not heatmap:
        finite = np.isfinite(value)
        if not finite.all():
            return (
                "misleading",
                f"image with {int((~finite).sum())} NaN/inf value(s), shown as black/white pixels",
                "replace them: np.nan_to_num(img, nan=0.0, posinf=1.0, neginf=0.0)",
            )
        low, high = float(value.min()), float(value.max())
        # mild saturation (an exposure gain) is the expected display; a range
        # that is off by a lot means the data is on another scale (0-255, signed)
        if low < -1.0 or high > 2.0:
            return (
                "misleading",
                f"float image in [{low:.3g}, {high:.3g}] is clipped to [0, 1]",
                "normalize it (e.g. (img - img.min()) / (img.max() - img.min())) or use "
                "layout.style(name, vmin=..., vmax=...) / a colormap",
            )
    return None


def output_problem(value: Any, style: Optional[dict] = None) -> Optional[Problem]:
    """Display problem of one output value, None when it is displayed faithfully."""
    if value is None or isinstance(value, str):
        return None
    if isinstance(value, np.ndarray):
        return array_problem(value, style)
    if _known_object(value):
        return None
    return (
        "unsupported",
        f"{type(value).__module__.split('.')[0]}.{type(value).__name__} is not a displayable type"
        if type(value).__module__ != "builtins"
        else f"{type(value).__name__} is not a displayable type",
        _object_fix(value),
    )


_VERBS = {
    "unsupported": "cannot be displayed",
    "gui": "is drawn by snapshot but not by every GUI backend",
    "misleading": "is displayed misleadingly",
}


def output_problems(named_values: Iterable[Tuple[str, Any]], styles: Optional[dict] = None) -> List[str]:
    """One message per output that is not displayed faithfully (``styles``: name -> layout.style options)."""
    messages = []
    for name, value in named_values:
        problem = output_problem(value, (styles or {}).get(name))
        if problem is None:
            continue
        severity, what, fix = problem
        verb = _VERBS[severity]
        messages.append(f"output '{name}' {verb}: {what}. Fix: {fix}.")
    return messages


def warn_output_problems(
    named_values: Iterable[Tuple[str, Any]], method: str = "snapshot", styles: Optional[dict] = None
) -> List[str]:
    """Log the problems (one warning) and return them."""
    messages = output_problems(named_values, styles)
    if messages:
        logging.warning(f"{method}(): " + " ".join(messages) + f" Displayable: {SUPPORTED_OUTPUTS}.")
    return messages
