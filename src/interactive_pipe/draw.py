"""Draw marks on images: points, boxes, lines, polygons, text and masks.

Small and dependency-free (numpy + Pillow, both required by
interactive_pipe; OpenCV is not needed). Meant to be called inside a filter::

    from interactive_pipe import draw

    @interactive(threshold=(0.5, [0.0, 1.0]))
    def detect(img, threshold=0.5):
        boxes = find_boxes(img, threshold)          # (N, 4) x0, y0, x1, y1
        return draw.boxes(img, boxes, labels=[f"{s:.2f}" for s in scores])

Conventions shared by every function:

- **Pure**: the input image is never modified (pipeline inputs are read-only
  views); a new array is returned.
- **dtype and range kept**: float images (values in ``[0, 1]``), ``uint8``
  (0-255) and ``uint16`` (0-65535) come back with the same dtype and range.
  Only the marked pixels change.
- **Channels**: RGB and RGBA images keep their channels (an RGBA image gets
  an opaque alpha where it is marked); grayscale ``(H, W)`` / ``(H, W, 1)``
  images are promoted to ``(H, W, 3)`` RGB, since marks are coloured.
- **Coordinates**: pixels, ``(x, y)`` order (x = column, y = row, origin at
  the top-left corner), sub-pixel values accepted. Marks partly or entirely
  outside the image are clipped, never an error; items with NaN coordinates
  are skipped.
- **Colours**: a name (``"red"``, ``"tab:blue"``), a hex string
  (``"#ff8800"``), an ``(r, g, b)`` tuple of floats in ``[0, 1]`` (or of ints
  in ``0-255`` when a value is above 1). ``color=None`` gives each item its
  own colour from ``DEFAULT_COLORS`` (matplotlib's ``tab10`` cycle); a list
  of colours is used per item (cycled when shorter).
"""

from functools import lru_cache
from typing import Any, List, Optional, Sequence, Tuple, Union

import numpy as np

__all__ = ["DEFAULT_COLORS", "points", "boxes", "lines", "polygon", "text", "mask", "to_rgb"]

# matplotlib's tab10 cycle
DEFAULT_COLORS: List[Tuple[float, float, float]] = [
    (0.122, 0.467, 0.706),
    (1.000, 0.498, 0.055),
    (0.173, 0.627, 0.173),
    (0.839, 0.153, 0.157),
    (0.580, 0.404, 0.741),
    (0.549, 0.337, 0.294),
    (0.890, 0.467, 0.761),
    (0.498, 0.498, 0.498),
    (0.737, 0.741, 0.133),
    (0.090, 0.745, 0.812),
]

# Text anchors: friendly names -> Pillow anchors (horizontal l/m/r, vertical t/m/b)
ANCHORS = {
    "top-left": "lt",
    "top": "mt",
    "top-right": "rt",
    "left": "lm",
    "center": "mm",
    "right": "rm",
    "bottom-left": "lb",
    "bottom": "mb",
    "bottom-right": "rb",
}

# Pillow draws with C ints: far away coordinates are brought back to this
# range (geometry only changes for values that are absurd anyway)
_COORD_LIMIT = 1e6

Color = Union[str, Sequence[float]]
ColorArg = Union[None, Color, Sequence[Color]]


# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------


def to_rgb(color: Color) -> Tuple[float, float, float]:
    """``(r, g, b)`` floats in ``[0, 1]`` from a colour name, a hex string or
    a tuple (floats in ``[0, 1]``, or ints in ``0-255`` when a value is > 1)."""
    if isinstance(color, str):
        from matplotlib.colors import to_rgb as mpl_to_rgb

        try:
            return tuple(float(c) for c in mpl_to_rgb(color))  # type: ignore[return-value]
        except ValueError:
            raise ValueError(f"Unknown colour {color!r}: use a name ('red'), a hex string or an (r, g, b) tuple")
    try:
        values = [float(c) for c in color]  # type: ignore[union-attr]
    except TypeError:
        raise TypeError(f"Colour must be a name, a hex string or an (r, g, b) tuple, got {color!r}")
    if len(values) not in (3, 4):
        raise ValueError(f"Colour tuple must have 3 (or 4) values, got {color!r}")
    values = values[:3]
    if max(values) > 1.0:
        values = [v / 255.0 for v in values]
    if min(values) < 0.0 or max(values) > 1.0:
        raise ValueError(f"Colour values must be in [0, 1] (or 0-255), got {color!r}")
    return (values[0], values[1], values[2])


def _is_single_color(color: Any) -> bool:
    if isinstance(color, str):
        return True
    if isinstance(color, np.ndarray):
        return color.ndim == 1
    try:
        first = color[0]
    except (TypeError, IndexError, KeyError):
        return False
    return isinstance(first, (int, float, np.integer, np.floating))


def _colors(color: ColorArg, count: int) -> List[Tuple[float, float, float]]:
    """One RGB colour per item: the default cycle, a single colour or a list (cycled)."""
    if color is None:
        palette = DEFAULT_COLORS
    elif _is_single_color(color):
        palette = [to_rgb(color)]  # type: ignore[arg-type]
    else:
        palette = [to_rgb(c) for c in color]  # type: ignore[union-attr]
        if not palette:
            raise ValueError("Empty colour list")
    return [palette[k % len(palette)] for k in range(count)]


def _text_color_on(background: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Black or white, whichever reads better on `background`."""
    luminance = 0.2126 * background[0] + 0.7152 * background[1] + 0.0722 * background[2]
    return (0.0, 0.0, 0.0) if luminance > 0.55 else (1.0, 1.0, 1.0)


# ---------------------------------------------------------------------------
# Canvas: marks are drawn on a transparent overlay, then blended
# ---------------------------------------------------------------------------


def _value_scale(img: np.ndarray) -> float:
    if img.dtype == np.uint8:
        return 255.0
    if img.dtype == np.uint16:
        return 65535.0
    if np.issubdtype(img.dtype, np.floating):
        return 1.0
    raise TypeError(f"Expected a float, uint8 or uint16 image, got dtype {img.dtype}")


def _check_image(img: Any) -> np.ndarray:
    if not isinstance(img, np.ndarray):
        raise TypeError(f"Expected a numpy image, got {type(img).__name__}")
    if img.ndim == 2 or (img.ndim == 3 and img.shape[-1] in (1, 3, 4)):
        _value_scale(img)
        return img
    raise ValueError(f"Expected an (H, W), (H, W, 1), (H, W, 3) or (H, W, 4) image, got shape {img.shape}")


def _as_rgb_copy(img: np.ndarray) -> np.ndarray:
    """New array with 3 (or 4) channels: grayscale is promoted to RGB."""
    if img.ndim == 3 and img.shape[-1] == 1:
        img = img[..., 0]
    if img.ndim == 2:
        return np.repeat(img[..., None], 3, axis=-1)
    return np.array(img, copy=True, order="C")  # C order: _blend writes through a reshape view


class _Canvas:
    """Where marks are drawn.

    - ``uint8`` gray / RGB images: directly on an RGB copy (Pillow blends the
      translucent fills), nothing else to do — the fast path;
    - other images (float, ``uint16``, RGBA): on a transparent RGBA overlay,
      blended into a copy by ``result()`` on the marked pixels only, so the
      rest of the image keeps its exact values.
    """

    def __init__(self, img: Any) -> None:
        from PIL import Image as PILImage
        from PIL import ImageDraw

        self.image = _check_image(img)
        self.height, self.width = self.image.shape[:2]
        self.direct = self.image.dtype == np.uint8 and (self.image.ndim == 2 or self.image.shape[-1] in (1, 3))
        if self.direct:
            self.overlay = PILImage.fromarray(np.ascontiguousarray(_as_rgb_copy(self.image)), "RGB")
            self.draw = ImageDraw.Draw(self.overlay, "RGBA")
        else:
            self.overlay = PILImage.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
            self.draw = ImageDraw.Draw(self.overlay)

    def rgba(self, color: Tuple[float, float, float], alpha: float = 1.0) -> Tuple[int, int, int, int]:
        """Pillow ink. On the overlay, colours are premultiplied by alpha: that
        is what Pillow produces when it antialiases text (or pastes through a
        mask) onto transparent pixels, so every mark is stored the same way."""
        alpha = min(max(float(alpha), 0.0), 1.0)
        weight = 1.0 if self.direct else alpha
        return (
            int(round(color[0] * weight * 255)),
            int(round(color[1] * weight * 255)),
            int(round(color[2] * weight * 255)),
            int(round(alpha * 255)),
        )

    def text_size(self, size: Optional[float]) -> int:
        if size is None:
            size = default_text_size(self.height, self.width)
        return max(int(round(size)), 6)

    def font(self, size: Optional[float]) -> Any:
        from interactive_pipe.graphical.display import get_font

        return get_font(self.text_size(size))

    def label(
        self,
        text: str,
        xy: Tuple[float, float],
        color: Tuple[float, float, float],
        size: int,
        anchor: str = "lb",
    ) -> None:
        """Text on a filled tag of `color` (labels of boxes and points).

        Tags are rendered once and cached: the same labels come back on
        every slider move."""
        tag, (dx, dy) = _label_tag(text, self.rgba(color), size, anchor)
        self.overlay.paste(tag, (int(round(xy[0] + dx)), int(round(xy[1] + dy))), tag)

    def result(self) -> np.ndarray:
        img = self.image
        if self.direct:
            return np.array(self.overlay)
        scale = _value_scale(img)
        out = _as_rgb_copy(img)
        overlay = np.asarray(self.overlay).reshape(-1, 4)
        flat = np.flatnonzero(overlay[:, 3])
        if flat.size == 0:
            return out
        marks = overlay[flat]
        compute = _compute_dtype(out)
        weight = marks[:, 3].astype(compute) / compute(255.0)
        # premultiplied overlay -> straight colours
        colors = np.clip(marks[:, :3].astype(compute) / (compute(255.0) * weight[:, None]), 0.0, 1.0)
        _blend(out, flat, colors, weight, scale)
        return out


def _compute_dtype(out: np.ndarray) -> Any:
    return np.float64 if out.dtype == np.float64 else np.float32


def _blend(out: np.ndarray, flat: np.ndarray, colors: np.ndarray, weight: np.ndarray, scale: float) -> None:
    """In place, on the pixels of flat indices `flat`:
    ``out = out * (1 - weight) + colors * weight`` (colors in [0, 1], one
    weight per pixel), rounded for integer images; an alpha channel becomes
    opaque in proportion."""
    compute = _compute_dtype(out)
    pixels = out.reshape(-1, out.shape[-1])  # a view: out is a fresh contiguous copy
    target = colors * compute(scale)
    if out.shape[-1] == 3 and bool((weight >= 1.0).all()):
        values = target  # opaque marks only (the common case): no blending
    else:
        under = pixels[flat, :3].astype(compute)
        values = under + (target - under) * weight[:, None]
    if np.issubdtype(out.dtype, np.integer):
        values = np.clip(np.rint(values), 0, scale)
    pixels[flat, :3] = values
    if out.shape[-1] == 4:
        under_alpha = pixels[flat, 3].astype(compute)
        new_alpha = under_alpha + (compute(scale) - under_alpha) * weight
        if np.issubdtype(out.dtype, np.integer):
            new_alpha = np.clip(np.rint(new_alpha), 0, scale)
        pixels[flat, 3] = new_alpha


@lru_cache(maxsize=1024)
def _label_tag(text: str, fill: Tuple[int, int, int, int], size: int, anchor: str) -> Tuple[Any, Tuple[int, int]]:
    """RGBA image of `text` on a `fill` box and its offset from the anchor point."""
    from PIL import Image as PILImage
    from PIL import ImageDraw

    from interactive_pipe.graphical.display import get_font

    font = get_font(size)
    probe = ImageDraw.Draw(PILImage.new("RGBA", (1, 1)))
    left, top, right, bottom = probe.textbbox((0, 0), text, font=font, anchor=anchor)
    pad = max(1, size // 6)
    width, height = int(np.ceil(right - left)) + 2 * pad, int(np.ceil(bottom - top)) + 2 * pad
    tag = PILImage.new("RGBA", (width, height), fill)
    background = (fill[0] / 255.0, fill[1] / 255.0, fill[2] / 255.0)
    ink = tuple(int(round(c * 255)) for c in _text_color_on(background)) + (255,)
    ImageDraw.Draw(tag).text((pad - left, pad - top), text, font=font, anchor=anchor, fill=ink)
    return tag, (int(np.floor(left)) - pad, int(np.floor(top)) - pad)


def default_text_size(height: int, width: int) -> int:
    """Default text height in pixels: readable on small and large images."""
    return int(np.clip(round(min(height, width) / 40.0), 12, 64))


# ---------------------------------------------------------------------------
# Coordinates
# ---------------------------------------------------------------------------


def _as_points(xy: Any, name: str = "xy") -> np.ndarray:
    """(N, 2) float array from one (x, y) pair or a sequence of them."""
    array = np.asarray(xy, dtype=np.float64)
    if array.ndim == 1 and array.size == 2:
        array = array[None, :]
    if array.size == 0:
        return np.zeros((0, 2))
    if array.ndim != 2 or array.shape[1] != 2:
        raise ValueError(f"{name} must be an (x, y) pair or an (N, 2) array of them, got shape {array.shape}")
    return np.clip(array, -_COORD_LIMIT, _COORD_LIMIT)


def _as_polylines(data: Any, name: str) -> List[np.ndarray]:
    """List of (M, 2) arrays: one (M, 2) polyline, a (K, M, 2) array (for
    instance K segments ``(K, 2, 2)``) or a list of (M_k, 2) polylines."""
    if isinstance(data, np.ndarray) or (
        isinstance(data, (list, tuple)) and data and not isinstance(data[0], np.ndarray)
    ):
        try:
            array = np.asarray(data, dtype=np.float64)
        except ValueError:  # ragged list of polylines
            array = None
        if array is not None and array.dtype != object:
            if array.size == 0:
                return []
            if array.ndim == 2 and array.shape[1] == 2:
                return [np.clip(array, -_COORD_LIMIT, _COORD_LIMIT)]
            if array.ndim == 3 and array.shape[2] == 2:
                return [np.clip(item, -_COORD_LIMIT, _COORD_LIMIT) for item in array]
            raise ValueError(
                f"{name} must be an (M, 2) polyline, a (K, M, 2) array or a list of (M, 2) arrays, "
                f"got shape {array.shape}"
            )
    return [_as_points(item, name) for item in data]


def _labels(labels: Any, count: int) -> List[Optional[str]]:
    if labels is None:
        return [None] * count
    if isinstance(labels, str):
        labels = [labels]
    labels = list(labels)
    if len(labels) != count:
        raise ValueError(f"Got {len(labels)} labels for {count} items")
    return [None if label is None else str(label) for label in labels]


def _finite(*values: float) -> bool:
    return all(np.isfinite(value) for value in values)


def _check_width(width: float, name: str = "width") -> int:
    if width <= 0:
        raise ValueError(f"{name} must be positive, got {width}")
    return max(1, int(round(width)))


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def points(
    img: np.ndarray,
    xy: Any,
    color: ColorArg = None,
    radius: float = 3.0,
    labels: Optional[Sequence[Any]] = None,
    filled: bool = True,
    width: float = 1.0,
    text_size: Optional[float] = None,
) -> np.ndarray:
    """Draw points (discs, or circles with ``filled=False``) at ``xy``.

    Args:
        img: image (not modified).
        xy: one ``(x, y)`` pair or an ``(N, 2)`` array of them, in pixels.
        color: one colour, a list (one per point) or None for the colour cycle.
        radius: disc radius in pixels (a radius below 1 marks a single pixel).
        labels: optional text per point, drawn on the right of the point.
        filled: discs (True) or circle outlines of ``width`` pixels (False).
        text_size: label height in pixels (default from the image size).

    Returns:
        A new image with the points drawn.
    """
    canvas = _Canvas(img)
    pts = _as_points(xy)
    colors = _colors(color, len(pts))
    texts = _labels(labels, len(pts))
    line_width = _check_width(width)
    label_size = canvas.text_size(text_size)
    for (x, y), rgb, label in zip(pts, colors, texts):
        if not _finite(x, y):
            continue
        fill = canvas.rgba(rgb)
        if radius < 1.0:
            canvas.draw.point((x, y), fill=fill)
        elif filled:
            canvas.draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=fill)
        else:
            canvas.draw.ellipse([x - radius, y - radius, x + radius, y + radius], outline=fill, width=line_width)
        if label:
            canvas.label(label, (x + max(radius, 1.0) + 3, y), rgb, label_size, anchor="lm")
    return canvas.result()


def boxes(
    img: np.ndarray,
    boxes: Any,
    labels: Optional[Sequence[Any]] = None,
    color: ColorArg = None,
    width: float = 2.0,
    fmt: str = "xyxy",
    text_size: Optional[float] = None,
) -> np.ndarray:
    """Draw rectangles.

    Args:
        img: image (not modified).
        boxes: one box or an ``(N, 4)`` array. ``fmt="xyxy"`` (default):
            ``(x0, y0, x1, y1)``, opposite corners in pixels; ``fmt="xywh"``:
            ``(x0, y0, width, height)``.
        labels: optional text per box, drawn on a filled tag above the box
            (inside it when the box touches the top of the image).
        color: one colour, a list (one per box) or None for the colour cycle.
        width: line width in pixels.
        fmt: ``"xyxy"`` or ``"xywh"``.
        text_size: label height in pixels (default from the image size).

    Returns:
        A new image with the boxes drawn.
    """
    if fmt not in ("xyxy", "xywh"):
        raise ValueError(f"fmt must be 'xyxy' or 'xywh', got {fmt!r}")
    canvas = _Canvas(img)
    array = np.asarray(boxes, dtype=np.float64)
    if array.size == 0:
        array = np.zeros((0, 4))
    if array.ndim == 1:
        array = array[None, :]
    if array.ndim != 2 or array.shape[1] != 4:
        raise ValueError(f"boxes must be a 4-value box or an (N, 4) array, got shape {array.shape}")
    array = array.copy()
    if fmt == "xywh":
        array[:, 2:] += array[:, :2]
    array = np.clip(array, -_COORD_LIMIT, _COORD_LIMIT)
    colors = _colors(color, len(array))
    texts = _labels(labels, len(array))
    line_width = _check_width(width)
    label_size = canvas.text_size(text_size)
    for (x0, y0, x1, y1), rgb, label in zip(array, colors, texts):
        if not _finite(x0, y0, x1, y1):
            continue
        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = min(y0, y1), max(y0, y1)
        canvas.draw.rectangle([x0, y0, x1, y1], outline=canvas.rgba(rgb), width=line_width)
        if label:
            if y0 - label_size - 2 >= 0:
                canvas.label(label, (max(x0, 0.0), y0 - 1), rgb, label_size, anchor="lb")
            else:  # no room above: inside the top-left corner (kept in the image)
                inside = (max(x0, 0.0) + line_width, max(y0, 0.0) + line_width + 1)
                canvas.label(label, inside, rgb, label_size, anchor="lt")
    return canvas.result()


def lines(
    img: np.ndarray,
    lines: Any,
    color: ColorArg = None,
    width: float = 2.0,
    closed: bool = False,
) -> np.ndarray:
    """Draw polylines or segments.

    Args:
        img: image (not modified).
        lines: one polyline ``(M, 2)`` (``(x, y)`` vertices), a ``(K, M, 2)``
            array — ``(K, 2, 2)`` is K segments — or a list of polylines of
            different lengths.
        color: one colour, a list (one per polyline) or None for the colour cycle.
        width: line width in pixels.
        closed: join the last vertex back to the first.

    Returns:
        A new image with the lines drawn.
    """
    canvas = _Canvas(img)
    polylines = _as_polylines(lines, "lines")
    colors = _colors(color, len(polylines))
    line_width = _check_width(width)
    for polyline, rgb in zip(polylines, colors):
        vertices = [(float(x), float(y)) for x, y in polyline if _finite(x, y)]
        if len(vertices) < 2:
            continue
        if closed and len(vertices) > 2:
            vertices.append(vertices[0])
        canvas.draw.line(vertices, fill=canvas.rgba(rgb), width=line_width, joint="curve" if line_width > 2 else None)
    return canvas.result()


def polygon(
    img: np.ndarray,
    polygons: Any,
    color: ColorArg = None,
    width: float = 2.0,
    fill_alpha: float = 0.0,
) -> np.ndarray:
    """Draw closed polygons, optionally filled with a translucent colour.

    Args:
        img: image (not modified).
        polygons: one polygon ``(M, 2)`` (``(x, y)`` vertices, M >= 3), a
            ``(K, M, 2)`` array or a list of polygons.
        color: one colour, a list (one per polygon) or None for the colour cycle.
        width: outline width in pixels (0: no outline, only the fill).
        fill_alpha: opacity of the fill, 0 (outline only, default) to 1.

    Returns:
        A new image with the polygons drawn.
    """
    if not 0.0 <= fill_alpha <= 1.0:
        raise ValueError(f"fill_alpha must be in [0, 1], got {fill_alpha}")
    if width < 0:
        raise ValueError(f"width must be >= 0, got {width}")
    canvas = _Canvas(img)
    shapes = _as_polylines(polygons, "polygons")
    colors = _colors(color, len(shapes))
    for shape, rgb in zip(shapes, colors):
        vertices = [(float(x), float(y)) for x, y in shape if _finite(x, y)]
        if len(vertices) < 3:
            continue
        if fill_alpha > 0:
            canvas.draw.polygon(vertices, fill=canvas.rgba(rgb, fill_alpha))
        if width > 0:
            outline = vertices + [vertices[0]]
            canvas.draw.line(outline, fill=canvas.rgba(rgb), width=_check_width(width), joint="curve")
    return canvas.result()


def text(
    img: np.ndarray,
    text: Union[str, Sequence[str]],
    xy: Any,
    color: ColorArg = "white",
    size: Optional[float] = None,
    anchor: str = "top-left",
    outline: Optional[Color] = "black",
    background: Optional[Color] = None,
    background_alpha: float = 0.6,
) -> np.ndarray:
    """Write text, readable on any image.

    By default the text is white with a thin black outline, readable on dark
    and bright areas alike; ``background=<colour>`` puts it on a translucent
    box instead (``outline=None`` to drop the outline).

    Args:
        img: image (not modified).
        text: one string, or a list of strings (one per position in ``xy``).
        xy: ``(x, y)`` of the anchor point, or an ``(N, 2)`` array.
        color: text colour (one, a list, or None for the colour cycle).
        size: text height in pixels (default from the image size, >= 12).
        anchor: which point of the text sits at ``xy``: ``"top-left"``
            (default), ``"top"``, ``"top-right"``, ``"left"``, ``"center"``,
            ``"right"``, ``"bottom-left"``, ``"bottom"``, ``"bottom-right"``,
            or a Pillow anchor such as ``"ls"`` (left, baseline).
        outline: colour of the outline around the letters, None for none.
        background: colour of a box behind the text, None for none.
        background_alpha: opacity of that box.

    Returns:
        A new image with the text written. Multi-line strings are supported.
    """
    pil_anchor = ANCHORS.get(anchor, anchor)
    if not isinstance(pil_anchor, str) or len(pil_anchor) != 2:
        raise ValueError(f"Unknown anchor {anchor!r}: use one of {sorted(ANCHORS)} or a Pillow anchor")
    canvas = _Canvas(img)
    texts = [text] if isinstance(text, str) else [str(item) for item in text]
    positions = _as_points(xy)
    if len(positions) != len(texts):
        raise ValueError(f"Got {len(texts)} texts for {len(positions)} positions")
    colors = _colors(color, len(texts))
    font = canvas.font(size)
    font_size = font.size if hasattr(font, "size") else 12
    stroke = max(1, int(round(font_size / 10.0))) if outline is not None and background is None else 0
    stroke_fill = canvas.rgba(to_rgb(outline)) if stroke else None
    for content, (x, y), rgb in zip(texts, positions, colors):
        if not _finite(x, y):
            continue
        item_anchor = pil_anchor
        if "\n" in content:  # multiline text: vertical anchors a (top) / m / d (bottom)
            item_anchor = pil_anchor[0] + {"t": "a", "b": "d", "s": "d"}.get(pil_anchor[1], pil_anchor[1])
        kwargs = {"font": font, "anchor": item_anchor}
        if background is not None:
            left, top, right, bottom = canvas.draw.textbbox((x, y), content, **kwargs)
            pad = max(2, font_size // 5)
            canvas.draw.rectangle(
                [left - pad, top - pad, right + pad, bottom + pad],
                fill=canvas.rgba(to_rgb(background), background_alpha),
            )
        canvas.draw.text((x, y), content, fill=canvas.rgba(rgb), stroke_width=stroke, stroke_fill=stroke_fill, **kwargs)
    return canvas.result()


def mask(
    img: np.ndarray,
    mask: np.ndarray,
    color: ColorArg = None,
    alpha: float = 0.5,
) -> np.ndarray:
    """Blend a mask over the image.

    Args:
        img: image (not modified).
        mask: ``(H, W)`` array, same height and width as the image:

            - boolean: True pixels get ``color`` (default: first colour of
              the cycle);
            - integer labels: 0 (and negatives) is background, each label
              ``k > 0`` gets its own colour — ``color=None`` cycles through
              ``DEFAULT_COLORS`` (label ``k`` -> colour ``(k - 1) % 10``),
              a list of colours is indexed the same way, one colour paints
              every label;
            - float in ``[0, 1]``: a soft mask, the per-pixel opacity is
              ``alpha * mask``.
        color: see above.
        alpha: opacity of the mask colour, 0 to 1.

    Returns:
        A new image with the mask blended in.
    """
    if not 0.0 <= alpha <= 1.0:
        raise ValueError(f"alpha must be in [0, 1], got {alpha}")
    image = _check_image(img)
    array = np.asarray(mask)
    if array.ndim == 3 and array.shape[-1] == 1:
        array = array[..., 0]
    if array.shape != image.shape[:2]:
        raise ValueError(f"mask shape {array.shape} does not match the image size {image.shape[:2]}")
    scale = _value_scale(image)
    out = _as_rgb_copy(image)
    compute = _compute_dtype(out)
    if array.dtype == np.bool_ or np.issubdtype(array.dtype, np.integer):
        if array.dtype == np.bool_:
            selected = array
            labels = None
        else:
            selected = array > 0
            labels = array.reshape(-1)[np.flatnonzero(selected)]
        flat = np.flatnonzero(selected)
        if flat.size == 0:
            return out
        if labels is None or (color is not None and _is_single_color(color)):
            rgb = np.asarray(_colors(color, 1)[0], dtype=compute)[None, :]
        else:
            palette = np.asarray(
                DEFAULT_COLORS if color is None else [to_rgb(c) for c in color],  # type: ignore[union-attr]
                dtype=compute,
            )
            rgb = palette[(labels.astype(np.int64) - 1) % len(palette)]
        weight = np.full(flat.size, alpha, dtype=compute)
    elif np.issubdtype(array.dtype, np.floating):
        soft = np.nan_to_num(np.clip(array, 0.0, 1.0)).astype(compute)
        flat = np.flatnonzero(soft)
        if flat.size == 0:
            return out
        if color is not None and not _is_single_color(color):
            raise ValueError("A float (soft) mask takes a single colour")
        rgb = np.asarray(_colors(color, 1)[0], dtype=compute)[None, :]
        weight = (alpha * soft.reshape(-1)[flat]).astype(compute)
    else:
        raise TypeError(f"mask must be boolean, integer labels or float, got dtype {array.dtype}")
    if rgb.shape[0] == 1:
        rgb = np.broadcast_to(rgb, (flat.size, 3))
    _blend(out, flat, rgb, weight, scale)
    return out
