"""Turn pipeline outputs into what every backend displays.

One place, shared by all the GUI backends (through
``InteractivePipeWindow.refresh_display``), the Gradio refresh path, the
headless snapshot renderer and the animation export, so an output looks the
same everywhere:

- ``display_kind`` classifies an output ("image", "signal", "curve", ...);
- ``prepare_display`` applies the output's ``layout.style`` options and
  returns a content the backends know how to draw.

No GUI toolkit is imported here.
"""

from typing import Any, Optional

import numpy as np

from interactive_pipe.data_objects.curves import Curve
from interactive_pipe.data_objects.table import Table


def display_kind(content: Any) -> Optional[str]:
    """Classify a pipeline output for display: "image" (2D/3D array), "signal"
    (1D array), "curve", "table", "text" or None when unsupported.

    Backends keep the kind of each canvas cell so that a filter switching
    output type between frames rebuilds the cell instead of feeding the new
    content to the previous widget/artist.
    """
    if isinstance(content, np.ndarray):
        return "signal" if content.ndim == 1 else "image"
    if isinstance(content, Curve):
        return "curve"
    if isinstance(content, Table):
        return "table"
    if isinstance(content, str):
        return "text"
    return None


HEATMAP_STYLE_KEYS = ("colormap", "vmin", "vmax")


def apply_display_style(content: Any, style: Optional[dict]) -> Any:
    """Apply the ``layout.style`` heatmap options to an output before display.

    A 2D ``(H, W)`` (or ``(H, W, 1)``) numpy array whose style sets
    ``colormap``, ``vmin`` or ``vmax`` is windowed to ``[vmin, vmax]``
    (each defaulting to the data min / max, as in matplotlib) and, with a
    colormap, turned into an ``(H, W, 3)`` RGB image in ``[0, 1]``. Anything
    else is returned unchanged.
    """
    if not isinstance(content, np.ndarray) or not style:
        return content
    if all(style.get(key) is None for key in HEATMAP_STYLE_KEYS):
        return content
    array = content[..., 0] if content.ndim == 3 and content.shape[-1] == 1 else content
    if array.ndim != 2 or not (np.issubdtype(array.dtype, np.number) or array.dtype == np.bool_):
        return content
    data = array.astype(np.float64)
    finite = data[np.isfinite(data)]
    vmin = style.get("vmin")
    vmax = style.get("vmax")
    if vmin is None:
        vmin = float(finite.min()) if finite.size else 0.0
    if vmax is None:
        vmax = float(finite.max()) if finite.size else 1.0
    span = vmax - vmin
    normalized = (data - vmin) / span if span != 0 else np.zeros_like(data)
    normalized = np.clip(normalized, 0.0, 1.0)
    colormap = style.get("colormap")
    if colormap is None:
        return normalized
    if isinstance(colormap, str):
        import matplotlib

        colormap = matplotlib.colormaps[colormap]
    return np.asarray(colormap(normalized))[..., :3]


def prepare_display(content: Any, style: Optional[dict] = None) -> Any:
    """What a backend should draw for one output, given its ``layout.style``.

    The single conversion point used by every backend and by the snapshot
    renderer: contents the backends draw natively (arrays, ``Curve``,
    ``Table``, ``str``) come out as such, with the style's display options
    applied. The pipeline result itself is never modified.
    """
    if isinstance(content, np.ndarray):
        return apply_display_style(content, style)
    return content
