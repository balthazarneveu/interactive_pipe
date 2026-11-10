"""Zoom/pan state of the Dear PyGui image grid (pure Python, no dpg import).

Mirrors the Qt ``ViewSync`` (qt_viewer.py): one state shared by every image
cell of a window so zoom & pan stay identical across cells. The zoom is a
multiplier on top of either the per-cell fit scale ("fit" family) or an
absolute 1 screen pixel per image pixel ("1:1" family); the view center is in
normalized image coordinates (0..1), so cells showing images of different
sizes stay consistently framed.

Each image cell is a fixed-size box (the drawlist sized by the grid layout);
``image_rect`` says where to draw the full image inside that box, the
drawlist clips what falls outside.
"""

from typing import Optional, Tuple

__all__ = ["ViewState", "VIEW_MODES", "ZOOM_STEP", "MIN_ZOOM", "MAX_ZOOM"]

VIEW_MODES = ("fit", "1:1")
ZOOM_STEP = 1.25
MIN_ZOOM = 1.0 / 64.0
MAX_ZOOM = 256.0

Size = Tuple[float, float]


class ViewState:
    """absolute: False -> zoom multiplies each cell's fit scale; True -> zoom is
    screen pixels per image pixel. center: normalized image coordinates of the
    point displayed at the middle of each cell."""

    def __init__(self) -> None:
        self.absolute = False
        self.zoom = 1.0
        self.center: Tuple[float, float] = (0.5, 0.5)

    @property
    def mode(self) -> str:
        """ "fit" / "1:1" when untouched, "custom" once zoomed or panned."""
        if self.zoom == 1.0 and self.center == (0.5, 0.5):
            return "1:1" if self.absolute else "fit"
        return "custom"

    def set_mode(self, mode: str) -> None:
        if mode not in VIEW_MODES:
            raise ValueError(f"view mode must be one of {VIEW_MODES}, got {mode!r}")
        self.absolute = mode == "1:1"
        self.zoom = 1.0
        self.center = (0.5, 0.5)

    def reset(self) -> None:
        self.set_mode("fit")

    def set_state(self, zoom: float, center: Tuple[float, float]) -> None:
        self.zoom = float(min(max(zoom, MIN_ZOOM), MAX_ZOOM))
        self.center = (float(center[0]), float(center[1]))

    # --- geometry (box = displayed cell size, size = image size, in pixels) ---
    @staticmethod
    def fit_scale(box: Size, size: Size) -> float:
        if size[0] <= 0 or size[1] <= 0:
            return 1.0
        return max(min(box[0] / size[0], box[1] / size[1]), 1e-6)

    def scale(self, box: Size, size: Size) -> float:
        """Screen pixels per image pixel."""
        base = 1.0 if self.absolute else self.fit_scale(box, size)
        return base * self.zoom

    def image_rect(self, box: Size, size: Size) -> Tuple[float, float, float, float]:
        """(x, y, width, height) of the drawn image in box coordinates."""
        s = self.scale(box, size)
        cu, cv = self.center
        return (box[0] / 2.0 - cu * size[0] * s, box[1] / 2.0 - cv * size[1] * s, size[0] * s, size[1] * s)

    def zoom_by(self, factor: float, box: Size, size: Size, anchor: Optional[Tuple[float, float]] = None) -> None:
        """Zoom by `factor` keeping the image point under `anchor` (box
        coordinates, default: box center) in place."""
        if size[0] <= 0 or size[1] <= 0:
            self.set_state(self.zoom * factor, self.center)
            return
        if anchor is None:
            anchor = (box[0] / 2.0, box[1] / 2.0)
        x0, y0, _, _ = self.image_rect(box, size)
        s = self.scale(box, size)
        fx, fy = (anchor[0] - x0) / s, (anchor[1] - y0) / s
        new_zoom = min(max(self.zoom * factor, MIN_ZOOM), MAX_ZOOM)
        base = 1.0 if self.absolute else self.fit_scale(box, size)
        new_scale = base * new_zoom
        cu = (fx - (anchor[0] - box[0] / 2.0) / new_scale) / size[0]
        cv = (fy - (anchor[1] - box[1] / 2.0) / new_scale) / size[1]
        self.set_state(new_zoom, (cu, cv))

    def pan_by(self, dx: float, dy: float, box: Size, size: Size) -> None:
        """Move the image by (dx, dy) screen pixels."""
        if size[0] <= 0 or size[1] <= 0:
            return
        s = self.scale(box, size)
        cu, cv = self.center
        self.set_state(self.zoom, (cu - dx / (s * size[0]), cv - dy / (s * size[1])))
