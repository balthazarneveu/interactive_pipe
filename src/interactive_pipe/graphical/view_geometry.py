"""Where an image cell draws its image for a zoom / pan state (pure Python).

Shared by the Qt (``qt_viewer``) and Dear PyGui (``dpg_viewer``) image grids.

An image may carry decorations that must not take part in the zoom: a heatmap
drawn with a colorbar is the (upscaled) map, possibly framed by axes,
followed by the colorbar strip on its right. ``CellContent`` describes this:

- ``strip``: width in image pixels of that strip (0: none). The strip stays
  fixed on the right of the map (at the right edge of the cell once zoomed
  in) and keeps the scale the whole image has when fitted; only the rest
  (the *main* part) zooms and pans, in the room the strip leaves.
- ``frame``: ``(x, y, width, height)`` of the data area inside the main part.
  The shared view center is in coordinates normalized over this frame, so
  cells whose data have the same size frame the same data pixels, whatever
  their decorations.

With neither (``CellContent.plain(width, height)``) the layout is the plain
one: fit / zoom / pan of the whole image, center normalized over it.

At zoom 1 (centered) the layout is exactly the one of the whole image
fitted to the cell: the strip right after the map, both centered.
"""

from typing import NamedTuple, Optional, Tuple

__all__ = [
    "CellContent",
    "CellLayout",
    "FIT_TOLERANCE",
    "MIN_ZOOM",
    "MAX_ZOOM",
    "cell_layout",
    "format_zoom",
    "zoom_center",
]

MIN_ZOOM = 1.0 / 64.0
MAX_ZOOM = 256.0
# screen pixels of slack when telling whether the image fits the view
FIT_TOLERANCE = 0.5

Size = Tuple[float, float]
Rect = Tuple[float, float, float, float]


class CellContent(NamedTuple):
    """Size of a displayed image and the parts of it that zoom (see module doc)."""

    width: int
    height: int
    strip: int = 0
    frame: Optional[Rect] = None

    @classmethod
    def plain(cls, width: float, height: float) -> "CellContent":
        return cls(int(width), int(height))

    @property
    def main_width(self) -> int:
        return max(self.width - self.strip, 1)

    @property
    def data_frame(self) -> Rect:
        if self.frame is None:
            return (0.0, 0.0, float(self.main_width), float(self.height))
        return self.frame


class CellLayout(NamedTuple):
    """Where to draw, in cell coordinates.

    ``main``: (x, y, w, h) of the main part (image columns ``[0, main_width)``),
    drawn at ``scale`` screen pixels per image pixel and clipped to ``room``
    (cell width / height left to it). ``strip``: (x, y, w, h) of the
    colorbar strip (image columns ``[main_width, width)``), drawn at
    ``strip_scale``; None without strip."""

    main: Rect
    scale: float
    room: Size
    strip: Optional[Rect]
    strip_scale: float

    def to_image(self, content: CellContent, px: float, py: float) -> Tuple[float, float]:
        """Cell coordinates -> continuous image pixel coordinates (columns of the
        strip are ``>= main_width``, so they never count as data)."""
        if self.strip is not None and px >= self.room[0]:
            sx, sy, _, _ = self.strip
            return (content.main_width + (px - sx) / self.strip_scale, (py - sy) / self.strip_scale)
        x0, y0, _, _ = self.main
        return ((px - x0) / self.scale, (py - y0) / self.scale)


def fit_scale(box: Size, size: Size) -> float:
    if size[0] <= 0 or size[1] <= 0:
        return 1.0
    return max(min(box[0] / size[0], box[1] / size[1]), 1e-6)


def _clamp(center: float, drawn: float, room: float) -> float:
    """Normalized center along one axis: 0.5 when the drawn image fits `room`,
    else limited so its edges do not come inside the room."""
    if drawn <= room + FIT_TOLERANCE:
        return 0.5
    half = room / (2.0 * drawn)
    return min(max(center, half), 1.0 - half)


def _strip_scale(box: Size, content: CellContent, absolute: bool) -> float:
    return 1.0 if absolute else fit_scale(box, (content.width, content.height))


def room(box: Size, content: CellContent, absolute: bool) -> Size:
    """Part of the cell the main part zooms in (the strip takes the rest)."""
    if content.strip <= 0:
        return box
    return (max(box[0] - content.strip * _strip_scale(box, content, absolute), 1.0), box[1])


def base_scale(box: Size, content: CellContent, absolute: bool) -> float:
    """Scale of the main part at zoom 1."""
    if absolute:
        return 1.0
    return fit_scale(room(box, content, absolute), (content.main_width, content.height))


def min_zoom(box: Size, content: CellContent, absolute: bool) -> float:
    """Smallest zoom: the main part fits its room (or stays at its current
    base scale when that is already smaller, e.g. a small image at 1:1)."""
    if content.width <= 0 or content.height <= 0:
        return MIN_ZOOM
    fit = fit_scale(room(box, content, absolute), (content.main_width, content.height))
    return max(MIN_ZOOM, min(1.0, fit / base_scale(box, content, absolute)))


def _main_center(content: CellContent, center: Tuple[float, float]) -> Tuple[float, float]:
    """Frame-normalized center -> normalized over the main part."""
    fx, fy, fw, fh = content.data_frame
    return ((fx + center[0] * fw) / content.main_width, (fy + center[1] * fh) / max(content.height, 1))


def _frame_center(content: CellContent, main: Tuple[float, float]) -> Tuple[float, float]:
    """Normalized over the main part -> frame-normalized center."""
    fx, fy, fw, fh = content.data_frame
    return ((main[0] * content.main_width - fx) / max(fw, 1e-9), (main[1] * content.height - fy) / max(fh, 1e-9))


def cell_layout(
    box: Size, content: CellContent, zoom: float, absolute: bool, center: Tuple[float, float]
) -> CellLayout:
    """Layout of `content` in a cell of size `box` for the shared view state."""
    room_w, room_h = room(box, content, absolute)
    s = base_scale(box, content, absolute) * zoom
    main_w, main_h = content.main_width * s, content.height * s
    cu, cv = _main_center(content, center)
    cu, cv = _clamp(cu, main_w, room_w), _clamp(cv, main_h, room_h)
    main = (room_w / 2.0 - cu * main_w, room_h / 2.0 - cv * main_h, main_w, main_h)
    if content.strip <= 0:
        return CellLayout(main, s, (room_w, room_h), None, 1.0)
    ss = _strip_scale(box, content, absolute)
    strip_w, strip_h = content.strip * ss, content.height * ss
    # right after the map; at the right edge of the cell once the map overflows its room
    strip = (min(main[0] + main_w, room_w), box[1] / 2.0 - strip_h / 2.0, strip_w, strip_h)
    return CellLayout(main, s, (room_w, room_h), strip, ss)


def clamped_center(
    box: Size, content: CellContent, zoom: float, absolute: bool, center: Tuple[float, float]
) -> Tuple[float, float]:
    """The frame-normalized center actually used by ``cell_layout`` (the image
    never leaves empty room in its cell that it could fill)."""
    room_w, room_h = room(box, content, absolute)
    s = base_scale(box, content, absolute) * zoom
    cu, cv = _main_center(content, center)
    return _frame_center(content, (_clamp(cu, content.main_width * s, room_w), _clamp(cv, content.height * s, room_h)))


def zoom_center(
    box: Size,
    content: CellContent,
    zoom: float,
    absolute: bool,
    center: Tuple[float, float],
    factor: float,
    anchor: Optional[Tuple[float, float]] = None,
) -> Tuple[float, Tuple[float, float]]:
    """New (zoom, frame-normalized center) after zooming by `factor`, keeping
    the image point under `anchor` (cell coordinates, default: the middle of
    the main part's room) in place."""
    layout = cell_layout(box, content, zoom, absolute, center)
    room_w, room_h = layout.room
    if anchor is None or (layout.strip is not None and anchor[0] >= room_w):
        anchor = (room_w / 2.0, room_h / 2.0)
    x0, y0, _, _ = layout.main
    fx, fy = (anchor[0] - x0) / layout.scale, (anchor[1] - y0) / layout.scale
    new_zoom = min(max(zoom * factor, min_zoom(box, content, absolute)), MAX_ZOOM)
    new_scale = base_scale(box, content, absolute) * new_zoom
    cu = (fx - (anchor[0] - room_w / 2.0) / new_scale) / content.main_width
    cv = (fy - (anchor[1] - room_h / 2.0) / new_scale) / max(content.height, 1)
    new_center = _frame_center(content, (cu, cv))
    return new_zoom, clamped_center(box, content, new_zoom, absolute, new_center)


def pan_center(
    box: Size, content: CellContent, zoom: float, absolute: bool, center: Tuple[float, float], dx: float, dy: float
) -> Tuple[float, float]:
    """Frame-normalized center after moving the image by (dx, dy) screen pixels."""
    s = base_scale(box, content, absolute) * zoom
    _, _, fw, fh = content.data_frame
    moved = (center[0] - dx / (s * max(fw, 1e-9)), center[1] - dy / (s * max(fh, 1e-9)))
    return clamped_center(box, content, zoom, absolute, moved)


def format_zoom(scale: float) -> str:
    """Screen pixels per image pixel as a percentage for the status line:
    ``"100%"``, ``"250%"``, ``"33%"``; one decimal below 10% (``"6.3%"``)."""
    percent = 100.0 * scale
    if percent >= 9.95:
        return f"{percent:.0f}%"
    return f"{percent:.1f}%"


def content_of(width: int, height: int, geometry: Optional[Tuple] = None) -> CellContent:
    """``CellContent`` of a displayed image of (width, height) pixels; `geometry`
    is its ``display.HeatmapGeometry`` (None: a plain image)."""
    if geometry is None or len(geometry) < 3:
        return CellContent.plain(width, height)
    upscale, data_h, data_w = geometry[:3]
    x0, y0 = (geometry[3], geometry[4]) if len(geometry) > 4 else (0, 0)
    main_width = getattr(geometry, "main_width", 0) or width
    strip = width - main_width if getattr(geometry, "colorbar", False) and 0 < main_width < width else 0
    frame = (float(x0), float(y0), float(data_w * upscale), float(data_h * upscale))
    return CellContent(int(width), int(height), int(strip), frame)
