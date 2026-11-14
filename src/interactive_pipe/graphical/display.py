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

from functools import lru_cache
from typing import Any, List, Optional, Tuple

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


# Style keys that make a 2D array a heatmap (``unit`` only decorates the colorbar)
HEATMAP_STYLE_KEYS = ("colormap", "vmin", "vmax", "center", "colorbar")

# NaN and masked pixels of a heatmap: a colour no common colormap uses, so a
# missing value never reads as a valid one. A Colormap object with its own
# ``set_bad`` colour (alpha > 0) overrides it.
BAD_COLOR = (1.0, 0.0, 1.0)

# Colorbar geometry. Text is drawn in display pixels, so a small map is first
# upscaled (nearest neighbour, integer factor) to at least COLORBAR_MIN_HEIGHT.
COLORBAR_MIN_HEIGHT = 256
COLORBAR_MAX_UPSCALE = 32
COLORBAR_FONT_FRACTION = 0.05  # label height relative to the map height
COLORBAR_FONT_MIN, COLORBAR_FONT_MAX = 12, 48


def _heatmap_array(content: Any, style: Optional[dict]) -> Optional[np.ndarray]:
    """The 2D array to show as a heatmap, None when the style or the content
    does not make a heatmap."""
    if not isinstance(content, np.ndarray) or not style:
        return None
    if all(style.get(key) in (None, False) for key in HEATMAP_STYLE_KEYS):
        return None
    array = content[..., 0] if content.ndim == 3 and content.shape[-1] == 1 else content
    if array.ndim != 2 or array.size == 0:
        return None
    if not (np.issubdtype(array.dtype, np.number) or array.dtype == np.bool_):
        return None
    return array


def heatmap_range(data: np.ndarray, valid: np.ndarray, style: dict) -> Tuple[float, float]:
    """(vmin, vmax) of a heatmap: the style values, each defaulting to the
    min / max of the valid (finite, unmasked) data; with ``center`` the range
    is widened to be symmetric around it."""
    finite = data[valid & np.isfinite(data)]
    vmin = style.get("vmin")
    vmax = style.get("vmax")
    if vmin is None:
        vmin = float(finite.min()) if finite.size else 0.0
    if vmax is None:
        vmax = float(finite.max()) if finite.size else 1.0
    center = style.get("center")
    if center is not None:
        half = max(abs(vmax - center), abs(vmin - center))
        vmin, vmax = center - half, center + half
    return float(vmin), float(vmax)


def colorbar_upscale(height: int) -> int:
    """Integer factor applied to a heatmap drawn with a colorbar, so the
    colorbar text stays legible on small maps (1 for maps tall enough)."""
    if height >= COLORBAR_MIN_HEIGHT:
        return 1
    return int(min(COLORBAR_MAX_UPSCALE, -(-COLORBAR_MIN_HEIGHT // max(height, 1))))


def heatmap_geometry(content: Any, style: Optional[dict]) -> Optional[Tuple[int, int, int]]:
    """``(upscale, height, width)`` of the data area of a heatmap displayed
    with a colorbar (pixel readouts map display pixels back to data pixels),
    None when the displayed image is pixel-aligned with the data."""
    array = _heatmap_array(content, style)
    if array is None or not style or not style.get("colorbar"):  # type: ignore[union-attr]
        return None
    height, width = array.shape
    return colorbar_upscale(height), height, width


def _resolve_colormap(colormap: Any) -> Any:
    if isinstance(colormap, str):
        import matplotlib

        return matplotlib.colormaps[colormap]
    return colormap


def _bad_color(colormap: Any) -> Tuple[float, float, float]:
    try:
        bad = colormap.get_bad()
    except AttributeError:
        return BAD_COLOR
    if len(bad) == 4 and bad[3] > 0:
        return (float(bad[0]), float(bad[1]), float(bad[2]))
    return BAD_COLOR


def apply_display_style(content: Any, style: Optional[dict]) -> Any:
    """Apply the ``layout.style`` heatmap options to an output before display.

    A 2D ``(H, W)`` (or ``(H, W, 1)``) numeric array whose style sets
    ``colormap``, ``vmin``, ``vmax``, ``center`` or ``colorbar`` is a heatmap:

    - it is windowed to ``[vmin, vmax]`` (each defaulting to the data min /
      max, as in matplotlib; ``center=c`` makes the range symmetric around
      ``c``) and, with a colormap, turned into an ``(H, W, 3)`` RGB image;
    - ``colorbar=True`` appends the scale on the right (gray colormap when
      none is given), with labelled ticks (``unit`` appended to each label).
      Small maps are upscaled first so the text stays legible;
    - NaN and masked values (``numpy.ma``) are drawn in ``BAD_COLOR``
      (magenta) — the output becomes RGB when there are any; ``+inf`` /
      ``-inf`` are clipped to the top / bottom of the scale.

    Anything else is returned unchanged.
    """
    array = _heatmap_array(content, style)
    if array is None or style is None:
        return content
    mask = np.ma.getmaskarray(array) if np.ma.isMaskedArray(array) else None
    data = np.asarray(np.ma.getdata(array), dtype=np.float64)
    invalid = np.isnan(data)
    if mask is not None:
        invalid |= mask
    vmin, vmax = heatmap_range(data, ~invalid, style)
    span = vmax - vmin
    normalized = (data - vmin) / span if span != 0 else np.zeros_like(data)
    normalized = np.clip(normalized, 0.0, 1.0)
    has_invalid = bool(invalid.any())
    if has_invalid:
        normalized[invalid] = 0.0
    colorbar = bool(style.get("colorbar"))
    colormap = style.get("colormap")
    if colormap is None:
        if not colorbar and not has_invalid:
            return normalized
        colormap = "gray"
    cmap = _resolve_colormap(colormap)
    rgb = np.asarray(cmap(normalized))[..., :3]
    if has_invalid:
        rgb[invalid] = _bad_color(cmap)
    if not colorbar:
        return rgb
    upscale = colorbar_upscale(rgb.shape[0])
    if upscale > 1:
        rgb = np.repeat(np.repeat(rgb, upscale, axis=0), upscale, axis=1)
    strip = colorbar_strip(cmap, vmin, vmax, rgb.shape[0], style.get("unit"))
    return np.concatenate([rgb, strip], axis=1)


# ---------------------------------------------------------------------------
# Colorbar drawn into the image (Pillow): identical on every backend
# ---------------------------------------------------------------------------


@lru_cache(maxsize=8)
def _font(size: int) -> Any:
    from PIL import ImageFont

    try:
        from matplotlib import font_manager

        path = font_manager.findfont(font_manager.FontProperties(family="DejaVu Sans"), fallback_to_default=True)
        return ImageFont.truetype(path, size)
    except (OSError, ValueError, ImportError):  # pragma: no cover - no FreeType / font file
        return ImageFont.load_default()


def _tick_step(vmin: float, vmax: float) -> Tuple[List[float], float]:
    """Round tick values inside [vmin, vmax] and their spacing."""
    from matplotlib.ticker import MaxNLocator

    if vmax <= vmin:
        return [], 0.0
    ticks = MaxNLocator(nbins=4).tick_values(vmin, vmax)
    step = float(ticks[1] - ticks[0]) if len(ticks) > 1 else vmax - vmin
    tolerance = 1e-9 * (vmax - vmin)
    return [float(t) for t in ticks if vmin - tolerance <= t <= vmax + tolerance], step


def _format_tick(value: float, step: float) -> str:
    """Tick label with as many decimals as the tick spacing needs."""
    if value == 0:
        return "0"
    magnitude = max(abs(value), step)
    if magnitude >= 1e5 or (step > 0 and step < 1e-4):
        return f"{value:.3g}"
    decimals = 0 if step <= 0 else max(0, int(-np.floor(np.log10(step))))
    text = f"{value:.{decimals}f}"
    return "0" if text in ("-0", "-0.0") else text


def _colorbar_labels(vmin: float, vmax: float, unit: Optional[str]) -> List[Tuple[float, str, bool]]:
    """(value, text, is_end) for the two ends and the round ticks between."""
    ticks, step = _tick_step(vmin, vmax)
    suffix = f" {unit}" if unit else ""
    ends = [vmin] if vmax == vmin else [vmin, vmax]
    labels = [(value, _format_tick(value, step / 10.0 if step else 0.0) + suffix, True) for value in ends]
    labels += [(value, _format_tick(value, step) + suffix, False) for value in ticks]
    return labels


def colorbar_strip(colormap: Any, vmin: float, vmax: float, height: int, unit: Optional[str] = None) -> np.ndarray:
    """``(height, w, 3)`` float RGB strip: a vertical colour scale from
    ``vmin`` (bottom) to ``vmax`` (top) with labelled ticks, on white."""
    key = colormap.name if hasattr(colormap, "name") and isinstance(colormap.name, str) else None
    if key is not None and _resolve_colormap(key) is not colormap:
        key = None  # a custom Colormap object sharing a registered name: do not cache
    if key is None:
        return _colorbar_strip(colormap, vmin, vmax, height, unit)
    return _cached_colorbar_strip(key, vmin, vmax, height, unit)


@lru_cache(maxsize=32)
def _cached_colorbar_strip(name: str, vmin: float, vmax: float, height: int, unit: Optional[str]) -> np.ndarray:
    strip = _colorbar_strip(_resolve_colormap(name), vmin, vmax, height, unit)
    strip.setflags(write=False)  # shared between calls
    return strip


def _colorbar_strip(colormap: Any, vmin: float, vmax: float, height: int, unit: Optional[str]) -> np.ndarray:
    from PIL import Image as PILImage
    from PIL import ImageDraw

    font_px = int(np.clip(round(height * COLORBAR_FONT_FRACTION), COLORBAR_FONT_MIN, COLORBAR_FONT_MAX))
    font = _font(font_px)
    gap = max(4, font_px // 2)
    bar_w = max(10, int(font_px * 1.2))
    tick_len = max(3, font_px // 4)
    bar_top = min(font_px, height // 4)
    bar_h = max(2, height - 2 * bar_top)
    labels = _colorbar_labels(vmin, vmax, unit)
    probe = ImageDraw.Draw(PILImage.new("RGB", (1, 1)))
    text_w = max((probe.textbbox((0, 0), text, font=font)[2] for _, text, _ in labels), default=0)
    label_x = gap + bar_w + tick_len + 2
    width = int(label_x + text_w + gap)

    strip = PILImage.new("RGB", (width, height), (255, 255, 255))
    gradient = np.asarray(colormap(np.linspace(1.0, 0.0, bar_h)))[:, :3]
    column = (gradient * 255.0 + 0.5).astype(np.uint8)
    strip.paste(PILImage.fromarray(np.ascontiguousarray(np.repeat(column[:, None, :], bar_w, axis=1))), (gap, bar_top))
    draw = ImageDraw.Draw(strip)
    draw.rectangle([gap - 1, bar_top - 1, gap + bar_w, bar_top + bar_h], outline=(0, 0, 0))

    span = vmax - vmin
    min_distance = font_px * 1.15
    placed: List[float] = []
    for value, text, is_end in sorted(labels, key=lambda item: not item[2]):  # ends first
        fraction = (value - vmin) / span if span else 0.5
        y = bar_top + (1.0 - fraction) * (bar_h - 1)
        if not is_end and any(abs(y - other) < min_distance for other in placed):
            continue  # would overlap a label already drawn
        placed.append(y)
        draw.line([gap + bar_w, y, gap + bar_w + tick_len, y], fill=(0, 0, 0))
        box = draw.textbbox((0, 0), text, font=font)
        draw.text((label_x, y - (box[1] + box[3]) / 2.0), text, font=font, fill=(0, 0, 0))
    return np.asarray(strip, dtype=np.float64) / 255.0


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
