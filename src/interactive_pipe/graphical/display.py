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

import warnings
from functools import lru_cache
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np

from interactive_pipe.data_objects.curves import Curve
from interactive_pipe.data_objects.image import Image
from interactive_pipe.data_objects.table import Table


def display_kind(content: Any) -> Optional[str]:
    """Classify a pipeline output for display: "image" (2D/3D array), "signal"
    (1D array), "curve", "table", "text", "figure" (matplotlib ``Figure`` or
    ``Axes``) or None when unsupported. ``prepare_display`` turns a "figure"
    into an "image", so backends never receive one.

    Backends keep the kind of each canvas cell so that a filter switching
    output type between frames rebuilds the cell instead of feeding the new
    content to the previous widget/artist.
    """
    if isinstance(content, np.ndarray):
        return "signal" if content.ndim == 1 else "image"
    if isinstance(content, Image):
        return display_kind(content.data) if isinstance(content.data, np.ndarray) else None
    if isinstance(content, Curve):
        return "curve"
    if isinstance(content, Table):
        return "table"
    if isinstance(content, str):
        return "text"
    if figure_of(content) is not None:
        return "figure"
    return None


def display_data(content: Any) -> Any:
    """The displayable payload of an output: an ``Image``'s array, else the
    content itself."""
    if isinstance(content, Image) and isinstance(content.data, np.ndarray):
        return content.data
    return content


def content_title(content: Any) -> Optional[str]:
    """Title carried by the output itself (``Image(..., title=...)``), used
    when ``layout.style`` sets none; None otherwise."""
    if isinstance(content, Image) and content.title:
        return str(content.title)
    return None


# ---------------------------------------------------------------------------
# matplotlib figures, rasterised with Agg in one place for every backend
# ---------------------------------------------------------------------------

# Resolution of a figure rasterised at its own ``figsize`` (Gradio, notebook,
# export_animation, a window cell not laid out yet): matplotlib's default
# 6.4 x 4.8 in figure gives 768 x 576 px. ``layout.style(name, dpi=...)``
# overrides it.
FIGURE_DPI = 120
# A figure shown in a cell of known size (Qt window, snapshots) is drawn at
# the cell size, keeping its aspect ratio, at this many pixels per inch: the
# dpi of the matplotlib canvas drawing a ``Curve`` in the Qt window, so the
# text of a figure and of a curve side by side come out the same size.
FIGURE_SCREEN_DPI = 100
MIN_FIGURE_BOX = 48  # smaller cells (not laid out yet): the figure keeps its figsize
_RASTER_ATTRIBUTE = "_interactive_pipe_raster"

Box = Tuple[float, float]


def fitted_figure_size(figsize: Sequence[float], dpi: float, box: Optional[Box]) -> Tuple[float, float]:
    """Size in inches at which a figure of `figsize` is rasterised: `figsize`
    itself without a usable `box`, else the largest size with the same aspect
    ratio fitting ``box`` = (width, height) pixels at `dpi`."""
    width, height = float(figsize[0]), float(figsize[1])
    if box is None or width <= 0 or height <= 0 or min(box) < MIN_FIGURE_BOX:
        return width, height
    factor = min(box[0] / (width * dpi), box[1] / (height * dpi))
    return width * factor, height * factor


def figure_of(content: Any) -> Any:
    """The root matplotlib ``Figure`` of a Figure / SubFigure / Axes, else None.

    matplotlib is only looked at when it is already imported: an output of
    another type never triggers the import.
    """
    import sys

    if "matplotlib.figure" not in sys.modules:
        return None
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure, SubFigure

    if isinstance(content, Axes):
        content = content.figure
    if isinstance(content, SubFigure):
        content = content.figure
    return content if isinstance(content, Figure) else None


def release_pyplot_figure(fig: Any) -> None:
    """Close `fig` in pyplot if pyplot manages it (``plt.subplots()``, ...).

    pyplot keeps every figure it creates until it is closed: a filter calling
    ``plt.subplots()`` on each slider move would leak one figure per run. A
    figure built with ``matplotlib.figure.Figure()`` is not registered and is
    left alone. The figure itself stays usable (it is redrawn with Agg).
    """
    import sys

    pyplot = sys.modules.get("matplotlib.pyplot")
    if pyplot is None:
        return
    number = getattr(fig, "number", None)
    manager = getattr(getattr(fig, "canvas", None), "manager", None)
    if manager is None and number is None:
        return
    from matplotlib._pylab_helpers import Gcf

    if any(registered.canvas.figure is fig for registered in Gcf.get_all_fig_managers()):
        pyplot.close(fig)


_DEFAULT_MARGINS_KEYS = ("left", "right", "bottom", "top", "wspace", "hspace")


def _default_margins() -> dict:
    import matplotlib

    return {key: matplotlib.rcParams[f"figure.subplot.{key}"] for key in _DEFAULT_MARGINS_KEYS}  # type: ignore[index]


def _no_layout_engine(fig: Any) -> bool:
    """No layout engine: None, or the placeholder ``Figure.tight_layout()``
    leaves behind (a previous rasterisation)."""
    from matplotlib.layout_engine import PlaceHolderLayoutEngine

    engine = fig.get_layout_engine()
    return engine is None or isinstance(engine, PlaceHolderLayoutEngine)


def _default_subplot_margins(fig: Any) -> bool:
    """True when the figure uses matplotlib's default subplot margins (no
    ``subplots_adjust``, no layout engine): they may be replaced for drawing."""
    params = fig.subplotpars
    return all(abs(getattr(params, key) - value) < 1e-9 for key, value in _default_margins().items())


def rasterize_figure(
    content: Any, dpi: Optional[float] = None, box: Optional[Box] = None, pixel_ratio: float = 1.0
) -> np.ndarray:
    """``(H, W, 3)`` float32 RGB image in ``[0, 1]`` of a matplotlib figure
    (or the figure of an Axes), drawn with Agg, transparency composited on
    white.

    - Without `box`: at the figure's ``figsize`` and `dpi` (``FIGURE_DPI`` by
      default): the text size relative to the figure depends on ``figsize``.
    - With ``box=(width, height)`` in pixels (the cell it is shown in): at the
      largest size of the same aspect ratio fitting the box, `dpi` defaulting
      to ``FIGURE_SCREEN_DPI``: a 10 pt label is 10 / 72 * dpi pixels high
      whatever the ``figsize``, like the text of a ``Curve``. The figure's own
      size is restored afterwards. `pixel_ratio` (device pixels per logical
      pixel, a HiDPI screen) multiplies the box and the dpi: same layout,
      sharper.

    The figure is released from pyplot first (see ``release_pyplot_figure``).
    The raster is kept on the figure and reused while the figure is unchanged
    (``fig.stale`` is False) and asked for at the same size — a cached filter
    output is not redrawn.
    """
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    fig = figure_of(content)
    if fig is None:
        raise TypeError(f"Expected a matplotlib Figure or Axes, got {type(content).__name__}")
    if dpi is None:
        dpi = FIGURE_DPI if box is None else FIGURE_SCREEN_DPI
    if box is not None and pixel_ratio != 1.0:
        dpi, box = dpi * pixel_ratio, (box[0] * pixel_ratio, box[1] * pixel_ratio)
    dpi = float(dpi)
    if dpi <= 0:
        raise ValueError(f"dpi must be positive, got {dpi}")
    release_pyplot_figure(fig)
    original_size = (float(fig.get_size_inches()[0]), float(fig.get_size_inches()[1]))
    size = fitted_figure_size(original_size, dpi, box)
    key = (dpi, round(size[0], 4), round(size[1], 4))
    cached = getattr(fig, _RASTER_ATTRIBUTE, None)
    if cached is not None and cached[0] == key and not fig.stale:
        return cached[1]
    canvas = fig.canvas if isinstance(fig.canvas, FigureCanvasAgg) else FigureCanvasAgg(fig)
    original_dpi = fig.dpi
    resized = size != original_size
    # a figure drawn smaller than its figsize keeps its text size: with the
    # default margins (fractions of the figure) the axis labels would be cut.
    # Fitted in a cell, a figure with default margins is always laid out tight
    # (the same picture whatever its figsize).
    fitted = box is not None and min(box) >= MIN_FIGURE_BOX
    auto_layout = fitted and _no_layout_engine(fig) and _default_subplot_margins(fig)
    try:
        fig.set_dpi(dpi)
        if resized:
            fig.set_size_inches(size, forward=False)
        if auto_layout:
            with warnings.catch_warnings():  # "not compatible with tight_layout": keep the default margins
                warnings.simplefilter("ignore", UserWarning)
                fig.tight_layout()
        canvas.draw()
        rgba = np.asarray(canvas.buffer_rgba())
        rgb = rgba[..., :3].astype(np.float32) / np.float32(255.0)
        alpha = rgba[..., 3]
        if (alpha < 255).any():
            weight = alpha[..., None].astype(np.float32) / np.float32(255.0)
            rgb = rgb * weight + (1.0 - weight)
    finally:
        if auto_layout:
            fig.subplots_adjust(**_default_margins())
        if resized:
            fig.set_size_inches(original_size, forward=False)
        fig.set_dpi(original_dpi)
    fig.stale = False  # set_dpi / set_size_inches mark it stale; the content did not change
    rgb.setflags(write=False)  # shared with the cache
    setattr(fig, _RASTER_ATTRIBUTE, (key, rgb))
    return rgb


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
COLORBAR_MAX_UPSCALED_WIDTH = 2048  # wide, flat maps are not blown up beyond this
COLORBAR_FONT_FRACTION = 0.05  # label height relative to the map height
COLORBAR_FONT_MIN, COLORBAR_FONT_MAX = 12, 48


def _heatmap_array(content: Any, style: Optional[dict]) -> Optional[np.ndarray]:
    """The 2D array to show as a heatmap, None when the style or the content
    does not make a heatmap."""
    if not isinstance(content, np.ndarray) or not style:
        return None
    # `is None`, not falsiness: vmin=0 / center=0 are real values
    if all(style.get(key) is None for key in ("colormap", "vmin", "vmax", "center")) and not style.get("colorbar"):
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
    # floats: numpy integer style values would wrap around in the arithmetic below
    vmin = None if style.get("vmin") is None else float(style["vmin"])
    vmax = None if style.get("vmax") is None else float(style["vmax"])
    if vmin is None:
        vmin = float(finite.min()) if finite.size else 0.0
    if vmax is None:
        vmax = float(finite.max()) if finite.size else 1.0
    center = None if style.get("center") is None else float(style["center"])
    if center is not None:
        half = max(abs(vmax - center), abs(vmin - center))
        vmin, vmax = center - half, center + half
    return float(vmin), float(vmax)


def colorbar_upscale(height: int, width: int = 1) -> int:
    """Integer factor applied to a heatmap drawn with a colorbar, so the
    colorbar text stays legible on small maps (1 for maps tall enough), never
    making the map wider than COLORBAR_MAX_UPSCALED_WIDTH."""
    if height >= COLORBAR_MIN_HEIGHT:
        return 1
    factor = min(COLORBAR_MAX_UPSCALE, -(-COLORBAR_MIN_HEIGHT // max(height, 1)))
    return int(max(1, min(factor, COLORBAR_MAX_UPSCALED_WIDTH // max(width, 1))))


def heatmap_geometry(content: Any, style: Optional[dict]) -> Optional[Tuple[int, int, int]]:
    """``(upscale, height, width)`` of the data area of a heatmap displayed
    with a colorbar (pixel readouts map display pixels back to data pixels),
    None when the displayed image is pixel-aligned with the data."""
    array = _heatmap_array(content, style)
    if array is None or not style or not style.get("colorbar"):  # type: ignore[union-attr]
        return None
    height, width = array.shape
    return colorbar_upscale(height, width), height, width


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
      none is given), with labelled ticks; ``unit`` is written once above the
      bar (with a ``x10^k`` multiplier for very large / small values);
      ``colorbar="some text"`` also writes that text vertically along the
      bar. Small maps are upscaled first so the text stays legible;
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
    # a constant map sits in the middle of the scale, where the colorbar puts its only label
    normalized = (data - vmin) / span if span != 0 else np.full_like(data, 0.5)
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
    upscale = colorbar_upscale(rgb.shape[0], rgb.shape[1])
    if upscale > 1:
        rgb = np.repeat(np.repeat(rgb, upscale, axis=0), upscale, axis=1)
    label = style.get("colorbar") if isinstance(style.get("colorbar"), str) else style.get("label")
    strip = colorbar_strip(cmap, vmin, vmax, rgb.shape[0], style.get("unit"), label)
    return np.concatenate([rgb, strip], axis=1)


# ---------------------------------------------------------------------------
# Colorbar drawn into the image (Pillow): identical on every backend
# ---------------------------------------------------------------------------


@lru_cache(maxsize=32)
def get_font(size: int) -> Any:
    """Pillow font of `size` pixels: matplotlib's bundled DejaVu Sans (always
    installed with matplotlib), Pillow's default font as a fallback."""
    from PIL import ImageFont

    try:
        from matplotlib import font_manager

        path = font_manager.findfont(font_manager.FontProperties(family="DejaVu Sans"), fallback_to_default=True)
        return ImageFont.truetype(path, size)
    except (OSError, ValueError, ImportError):  # pragma: no cover - no FreeType / font file
        return ImageFont.load_default()


def _tick_step(vmin: float, vmax: float) -> Tuple[List[float], float]:
    """Round tick values (1, 2 or 5 x 10^k apart) inside [vmin, vmax] and their spacing."""
    from matplotlib.ticker import MaxNLocator

    if vmax <= vmin:
        return [], 0.0
    ticks = MaxNLocator(nbins=4, steps=[1, 2, 5, 10]).tick_values(vmin, vmax)
    step = float(ticks[1] - ticks[0]) if len(ticks) > 1 else vmax - vmin
    tolerance = 1e-9 * (vmax - vmin)
    return [float(t) for t in ticks if vmin - tolerance <= t <= vmax + tolerance], step


_SUPERSCRIPT = str.maketrans("-0123456789", "\u207b\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079")
COLORBAR_MAX_DECIMALS = 6
COLORBAR_END_TOLERANCE = 0.005  # an end label is at most 0.5 % of the range away from the true value


def _decimals(values: Sequence[float], tolerance: float) -> int:
    """Fewest decimals writing every value within `tolerance`."""
    for decimals in range(COLORBAR_MAX_DECIMALS + 1):
        if all(abs(round(value, decimals) - value) <= tolerance for value in values):
            return decimals
    return COLORBAR_MAX_DECIMALS


def _fixed(value: float, decimals: int) -> str:
    text = f"{value:.{decimals}f}"
    return text[1:] if text.startswith("-") and float(text) == 0 else text  # no "-0.00"


def colorbar_scale(vmin: float, vmax: float) -> Tuple[List[Tuple[float, str, bool]], int]:
    """Labels of a colorbar and its power-of-ten multiplier.

    Returns ``([(value, text, is_end), ...], exponent)``: the two ends (one
    for a constant map) and the round ticks between, all written with the
    same number of decimals, as ``value / 10**exponent``. ``exponent`` is 0
    unless the values are very large (>= 1e5) or very small (< 1e-2), when
    the bar shows ``x10^exponent`` once at its top instead of ``1e-03`` on
    every tick. The ends get enough decimals to be within 0.5 % of the range
    of the true value (``4.2``, not ``4``)."""
    largest = max(abs(vmin), abs(vmax))
    exponent = 0
    if largest >= 1e5 or 0 < largest < 1e-2:
        exponent = int(np.floor(np.log10(largest)))
    scale = 10.0**exponent
    low, high = vmin / scale, vmax / scale
    if high == low:
        return [(vmin, f"{low:.4g}", True)], exponent
    ticks, step = _tick_step(low, high)
    decimals = max(
        _decimals(ticks, 1e-6 * step),
        _decimals([low, high], COLORBAR_END_TOLERANCE * (high - low)),
    )
    labels = [(value * scale, _fixed(value, decimals), True) for value in (low, high)]
    labels += [(value * scale, _fixed(value, decimals), False) for value in ticks]
    return labels, exponent


def place_colorbar_labels(
    labels: List[Tuple[float, str, bool]], vmin: float, vmax: float, bar_top: float, bar_h: int, min_distance: float
) -> List[Tuple[float, str]]:
    """``(y, text)`` of the labels drawn: the ends always, a round tick only
    when it is at least `min_distance` pixels from every label kept."""
    span = vmax - vmin
    placed: List[Tuple[float, str]] = []
    for value, text, is_end in sorted(labels, key=lambda item: not item[2]):  # ends first: never dropped
        fraction = (value - vmin) / span if span else 0.5
        y = bar_top + (1.0 - fraction) * (bar_h - 1)
        if not is_end and any(abs(y - other) < min_distance for other, _ in placed):
            continue  # a round tick too close to a label already drawn
        placed.append((y, text))
    return placed


def colorbar_header(exponent: int, unit: Optional[str]) -> str:
    """Text above the bar: the multiplier (``\u00d710\u207b\u00b3``) and the unit, once."""
    parts = []
    if exponent:
        parts.append("\u00d710" + str(exponent).translate(_SUPERSCRIPT))
    if unit:
        parts.append(str(unit))
    return " ".join(parts)


def colorbar_strip(
    colormap: Any,
    vmin: float,
    vmax: float,
    height: int,
    unit: Optional[str] = None,
    label: Optional[str] = None,
) -> np.ndarray:
    """``(height, w, 3)`` float RGB strip: a vertical colour scale from
    ``vmin`` (bottom) to ``vmax`` (top) with labelled ticks, on white; the
    unit (and a power-of-ten multiplier) once above the bar, ``label``
    written vertically along it."""
    import matplotlib

    key = getattr(colormap, "name", None)
    # cache only registered colormaps (the registry hands out equal copies);
    # a custom Colormap, possibly sharing a registered name, is drawn each time
    if not isinstance(key, str) or key not in matplotlib.colormaps or matplotlib.colormaps[key] != colormap:
        key = None
    if key is None:
        return _colorbar_strip(colormap, vmin, vmax, height, unit, label)
    return _cached_colorbar_strip(key, vmin, vmax, height, unit, label)


@lru_cache(maxsize=32)
def _cached_colorbar_strip(
    name: str, vmin: float, vmax: float, height: int, unit: Optional[str], label: Optional[str]
) -> np.ndarray:
    strip = _colorbar_strip(_resolve_colormap(name), vmin, vmax, height, unit, label)
    strip.setflags(write=False)  # shared between calls
    return strip


def _colorbar_strip(
    colormap: Any, vmin: float, vmax: float, height: int, unit: Optional[str], label: Optional[str]
) -> np.ndarray:
    from PIL import Image as PILImage
    from PIL import ImageDraw

    font_px = int(np.clip(round(height * COLORBAR_FONT_FRACTION), COLORBAR_FONT_MIN, COLORBAR_FONT_MAX))
    font = get_font(font_px)
    gap = max(4, font_px // 2)
    bar_w = max(10, int(font_px * 1.2))
    tick_len = max(3, font_px // 4)
    labels, exponent = colorbar_scale(vmin, vmax)
    header = colorbar_header(exponent, unit)
    probe = ImageDraw.Draw(PILImage.new("RGB", (1, 1)))
    header_h = font_px + max(2, font_px // 3) if header else 0
    # room above the bar for the header, then half a label (the top end is centred on the bar's top)
    bar_top = min(header_h + font_px, height // 3) if header else min(font_px, height // 4)
    bar_bottom = min(font_px, height // 4)
    bar_h = max(2, height - bar_top - bar_bottom)
    text_w = max((probe.textbbox((0, 0), text, font=font)[2] for _, text, _ in labels), default=0)
    label_x = gap + bar_w + tick_len + max(3, font_px // 3)  # clear of the tick: '-0.5' must not read '--0.5'
    width = int(label_x + text_w + gap)
    side = None
    if label:
        box = probe.textbbox((0, 0), str(label), font=font)
        side = PILImage.new("RGB", (int(box[2]) + 2, int(box[3]) + 2), (255, 255, 255))
        ImageDraw.Draw(side).text((1, 1), str(label), font=font, fill=(0, 0, 0))
        side = side.rotate(90, expand=True)  # reads bottom to top, like matplotlib's colorbar label
        if side.height > height:  # longer than the map: cropped rather than shrunk
            side = side.crop((0, (side.height - height) // 2, side.width, (side.height + height) // 2))
        width += side.width + gap
    if header:
        width = max(width, int(gap + probe.textbbox((0, 0), header, font=font)[2] + gap))

    strip = PILImage.new("RGB", (width, height), (255, 255, 255))
    gradient = np.asarray(colormap(np.linspace(1.0, 0.0, bar_h)))[:, :3]
    column = (gradient * 255.0 + 0.5).astype(np.uint8)
    strip.paste(PILImage.fromarray(np.ascontiguousarray(np.repeat(column[:, None, :], bar_w, axis=1))), (gap, bar_top))
    draw = ImageDraw.Draw(strip)
    draw.rectangle([gap - 1, bar_top - 1, gap + bar_w, bar_top + bar_h], outline=(0, 0, 0))
    if header:
        draw.text((gap - 1, max(0, bar_top - font_px - header_h)), header, font=font, fill=(0, 0, 0))
    if side is not None:
        strip.paste(side, (width - gap - side.width, bar_top + (bar_h - side.height) // 2))

    for y, text in place_colorbar_labels(labels, vmin, vmax, bar_top, bar_h, font_px * 1.15):
        draw.line([gap + bar_w, y, gap + bar_w + tick_len, y], fill=(0, 0, 0))
        box = draw.textbbox((0, 0), text, font=font)
        draw.text((label_x, y - (box[1] + box[3]) / 2.0), text, font=font, fill=(0, 0, 0))
    return np.asarray(strip, dtype=np.float64) / 255.0


# ---------------------------------------------------------------------------
# Text outputs (str): one size and wrapping rule for every backend
# ---------------------------------------------------------------------------

# Text cells (str outputs: readouts, metrics) are written larger than titles
TEXT_FONT_PT = 12
TEXT_CHAR_WIDTH = 0.6  # average character width, in font heights (DejaVu Sans)


def wrap_text(text: str, width: float, font_size: float) -> str:
    """`text` wrapped to lines of about `width` (same unit as `font_size`:
    pixels, or points). Existing line breaks are kept; a word longer than a
    line is cut only if it would not fit at all."""
    import textwrap

    max_chars = max(8, int(width / (font_size * TEXT_CHAR_WIDTH)))
    lines = []
    for line in str(text).splitlines() or [""]:
        lines.extend(textwrap.wrap(line, max_chars, break_long_words=True, break_on_hyphens=False) or [""])
    return "\n".join(lines)


class DisplayError(ValueError):
    """An output array that cannot be displayed without guessing its layout
    (channel-first, batch, empty, object / complex dtype...). The message names
    the output (and the filter returning it) and the fix. Raised by
    ``prepare_display``: by ``snapshot`` / ``sweep``; a GUI window shows the
    message in the cell instead and keeps running."""


# Size of a checkerboard square behind transparent pixels, relative to the
# largest side of the image (at least CHECKER_MIN_SQUARE pixels)
CHECKER_FRACTION = 1.0 / 32.0
CHECKER_MIN_SQUARE = 4
CHECKER_LIGHT, CHECKER_DARK = 0.8, 0.6


def _describe_output(name: Optional[str], filter_name: Optional[str]) -> str:
    if name is None:
        return "output"
    if filter_name is None or filter_name == name:
        return f"output '{name}'"
    return f"output '{name}' (returned by filter '{filter_name}')"


def array_display_problem(array: np.ndarray) -> Optional[Tuple[str, str]]:
    """``(problem, fix)`` when `array` cannot be displayed without guessing,
    None when ``prepare_display`` shows it. 1D arrays are signals (curves)."""
    shape = tuple(array.shape)
    if array.size == 0:
        return f"empty array {shape}", "return a non-empty array, or None for an empty cell"
    kind = array.dtype.kind
    if kind == "c":
        return f"complex array {shape}", "return a real array, e.g. np.abs(z) or np.angle(z)"
    if kind not in "biuf":
        return (
            f"{array.dtype} array {shape} (not numbers)",
            "return a numeric array (convert with img.astype(np.float32)), or a str for text",
        )
    if array.ndim == 0:
        return "0D array (a scalar)", "display it as text: return f'{float(value):.3f}'"
    if array.ndim > 3:
        return f"{array.ndim}D array {shape}", "return one image (e.g. batch[0]) or one output per image"
    if array.ndim == 3 and shape[-1] not in (1, 3, 4):
        if shape[0] in (1, 3, 4):
            fix = "move the channels last: np.moveaxis(img, 0, -1)"
            if shape[0] == 1:
                fix = "drop the channel axis: img[0]"
            return f"channel-first array {shape}", fix
        return f"{shape[-1]}-channel array {shape}", "return (H, W), (H, W, 3) RGB or (H, W, 4) RGBA"
    return None


def check_displayable(array: np.ndarray, name: Optional[str] = None, filter_name: Optional[str] = None) -> None:
    """Raise ``DisplayError`` naming the output when `array` cannot be displayed."""
    problem = array_display_problem(array)
    if problem is not None:
        what, fix = problem
        raise DisplayError(f"{_describe_output(name, filter_name)} cannot be displayed: {what}. Fix: {fix}.")


def checkerboard(height: int, width: int) -> np.ndarray:
    """``(H, W)`` float gray checkerboard shown behind transparent pixels."""
    square = max(CHECKER_MIN_SQUARE, int(round(max(height, width) * CHECKER_FRACTION)))
    rows = (np.arange(height) // square)[:, None]
    cols = (np.arange(width) // square)[None, :]
    return np.where((rows + cols) % 2 == 0, CHECKER_LIGHT, CHECKER_DARK).astype(np.float32)


def normalize_image(array: np.ndarray) -> np.ndarray:
    """A displayable 2D / 3D array as the ``(H, W, 3)`` float RGB image every
    backend draws (values outside [0, 1] are clipped later by the backends):

    - ``(H, W)`` and ``(H, W, 1)`` -> gray RGB (no colormap: use
      ``layout.style(name, colormap=...)`` for a false-colour heatmap);
    - ``bool`` -> 0 / 1; ``uint8`` -> / 255; ``uint16`` -> / 65535; other
      integer types are taken as values, like floats (``1`` is white);
    - ``(H, W, 4)`` RGBA -> composited on a gray checkerboard (opaque pixels
      unchanged).

    Float RGB arrays are returned as is (no copy).
    """
    array = np.ma.getdata(array)
    if array.dtype == np.uint8:
        array = array.astype(np.float32) / np.float32(255.0)
    elif array.dtype == np.uint16:
        array = array.astype(np.float32) / np.float32(65535.0)
    elif array.dtype.kind in "biu":
        array = array.astype(np.float32)
    if array.ndim == 3 and array.shape[-1] == 1:
        array = array[..., 0]
    if array.ndim == 2:
        return np.repeat(array[..., None], 3, axis=-1)
    if array.shape[-1] == 4:
        alpha = np.clip(array[..., 3:4], 0.0, 1.0)
        background = checkerboard(*array.shape[:2])[..., None]
        return array[..., :3] * alpha + background * (1.0 - alpha)
    return array


def prepare_display(
    content: Any,
    style: Optional[dict] = None,
    name: Optional[str] = None,
    filter_name: Optional[str] = None,
    box: Optional[Box] = None,
    pixel_ratio: float = 1.0,
) -> Any:
    """What a backend should draw for one output, given its ``layout.style``.

    The single conversion point used by every backend and by the snapshot
    renderer: contents the backends draw natively (``Curve``, ``Table``,
    ``str``, 1D signals) come out as such; an ``Image`` is shown as its array;
    a matplotlib ``Figure`` / ``Axes`` becomes an RGB image
    (``rasterize_figure``, at the size of its cell when the caller knows it:
    ``box=(width, height)`` logical pixels, `pixel_ratio` device pixels per
    logical pixel); a 2D / 3D array gets its heatmap style applied
    (``apply_display_style``) and becomes an ``(H, W, 3)`` float RGB image
    (``normalize_image``: gray, uint8 / uint16 / bool scaling, RGBA on a
    checkerboard). An array whose layout cannot be guessed raises
    ``DisplayError`` naming the output (`name`, `filter_name`) and the fix.
    The pipeline result itself is never modified.
    """
    content = display_data(content)
    if isinstance(content, np.ndarray):
        check_displayable(content, name, filter_name)
        if content.ndim == 1:
            return content
        styled = apply_display_style(content, style)
        return normalize_image(styled)
    if figure_of(content) is not None:
        return rasterize_figure(content, (style or {}).get("dpi"), box, pixel_ratio)
    return content


def producer_of(filters: Any, output_name: Any) -> Optional[str]:
    """Name of the filter (in `filters`) returning the output `output_name`, None if unknown."""
    for filt in filters or []:
        if output_name in (getattr(filt, "outputs", None) or []):
            return getattr(filt, "name", None)
    return None
