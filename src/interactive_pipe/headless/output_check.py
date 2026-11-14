"""Can an output be displayed, and will it look like what the filter meant?

The GUI backends and the snapshot renderer share one conversion
(``graphical.display.prepare_display``): arrays it cannot interpret raise a
``DisplayError`` there, other types are drawn as a placeholder, and some
arrays are displayed misleadingly (a float image in 0-255 clipped to [0, 1] is
white, NaN is black). ``output_problems`` names these cases with the fix;
``snapshot`` and ``sweep`` log them, so an agent looking at the PNG knows why
a cell is empty or saturated. Detection only: no output is converted here.
"""

import logging
from typing import Any, Iterable, List, Optional, Tuple

import numpy as np

from interactive_pipe.data_objects.image import Image
from interactive_pipe.graphical.display import array_display_problem, figure_of

SUPPORTED_OUTPUTS = (
    "numpy images (H, W), (H, W, 1), (H, W, 3) or (H, W, 4) - float in [0, 1], uint8, uint16 or bool -, "
    "1D numpy arrays (drawn as curves), Image, Curve, SingleCurve, Table, str, matplotlib Figure / Axes, "
    "and None (empty cell)"
)

#: (severity, problem, fix) - severity is "unsupported" (drawn nowhere) or "misleading" (drawn wrong everywhere)
Problem = Tuple[str, str, str]


def _known_object(value: Any) -> bool:
    try:
        from interactive_pipe.data_objects.curves import Curve, SingleCurve
        from interactive_pipe.data_objects.table import Table
    except ImportError:  # pragma: no cover - optional dependencies
        return False
    return isinstance(value, (Curve, SingleCurve, Table)) or figure_of(value) is not None


def _object_fix(value: Any) -> str:
    module = type(value).__module__.split(".")[0]
    name = type(value).__name__
    if module == "torch":
        return "convert it in the filter: `return tensor.detach().cpu().numpy()` (channels last, (H, W, 3))"
    if module == "PIL":
        return "convert it in the filter: `return np.asarray(pil_image)` (uint8 is scaled by 1/255)"
    if module == "matplotlib":
        return "return the Figure (`fig`) or the Axes (`ax`), or the data (numpy array, Curve)"
    if isinstance(value, dict):
        return "return the arrays as separate outputs (`return a, b`), or a Table for tabular data"
    if isinstance(value, (list, tuple)):
        return "return the elements as separate outputs (`return a, b`), unpacked in the pipeline (`a, b = f(x)`)"
    if isinstance(value, (bool, int, float, complex, np.generic)):
        return "display it as text (`return f'{value:.3f}'`) or as a curve / image"
    return f"convert the {name} to a numpy array, a Curve or a Table in the filter"


HEATMAP_STYLE_KEYS = ("colormap", "vmin", "vmax", "center", "colorbar")


def array_problem(value: np.ndarray, style: Optional[dict] = None) -> Optional[Problem]:
    """Display problem of a numpy array, None when it is displayed faithfully.

    ``style``: the output's ``layout.style`` options; a heatmap style
    (colormap / vmin / vmax / center / colorbar) maps any value range itself.
    """
    unsupported = array_display_problem(value)
    if unsupported is not None:
        return ("unsupported", unsupported[0], unsupported[1])
    if value.ndim == 1:
        return None  # drawn as a curve
    shape = value.shape
    heatmap = (
        (value.ndim == 2 or shape[-1] == 1)
        and bool(style)
        and any(style.get(key) is not None for key in HEATMAP_STYLE_KEYS)  # type: ignore[union-attr]
    )
    if heatmap or value.dtype.kind == "b" or value.dtype in (np.uint8, np.uint16):
        return None  # scaled by the display (uint8 / 255, uint16 / 65535, bool 0 / 1)
    styled = sorted(key for key in HEATMAP_STYLE_KEYS if style and style.get(key) is not None)
    # the usual fix is a heatmap style; when one is already there it is ignored
    # because the array is not 2D: say that instead of suggesting it again
    style_fix = (
        "layout.style(name, vmin=..., vmax=...) / a colormap"
        if not styled
        else f"note: layout.style({', '.join(styled)}) applies to 2D (H, W) arrays only, this one is {shape}"
    )
    data = np.ma.getdata(value)
    if value.dtype.kind in "iu":
        low, high = int(data.min()), int(data.max())
        if low < 0 or high > 1:
            return (
                "misleading",
                f"{value.dtype} image in [{low}, {high}]: integers other than uint8 / uint16 are taken as values "
                "(1 is white) and clipped to [0, 1]",
                "scale it (e.g. img / 255.0, or img.astype(np.uint8) for 0-255 data)"
                + (" or use " if not styled else "; ")
                + style_fix,
            )
        return None
    finite = np.isfinite(data)
    if not finite.all():
        return (
            "misleading",
            f"image with {int((~finite).sum())} NaN/inf value(s), shown as black/white pixels",
            "replace them: np.nan_to_num(img, nan=0.0, posinf=1.0, neginf=0.0), "
            "or use layout.style(name, colormap=...) to show NaN in magenta",
        )
    low, high = float(data.min()), float(data.max())
    # mild saturation (an exposure gain) is the expected display; a range
    # that is off by a lot means the data is on another scale (0-255, signed)
    if low < -1.0 or high > 2.0:
        return (
            "misleading",
            f"float image in [{low:.3g}, {high:.3g}] is clipped to [0, 1]",
            "normalize it (e.g. (img - img.min()) / (img.max() - img.min()))"
            + (" or use " if not styled else "; ")
            + style_fix,
        )
    return None


def output_problem(value: Any, style: Optional[dict] = None) -> Optional[Problem]:
    """Display problem of one output value, None when it is displayed faithfully."""
    if value is None or isinstance(value, str):
        return None
    if isinstance(value, Image) and isinstance(value.data, np.ndarray):
        value = value.data
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
