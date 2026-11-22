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

Zooming out stops at the size that fits the cell (or at the native size when
that is smaller, in "1:1"), and along an axis where the image fits the cell it
stays centered; zoomed in, it pans no further than its edges: the image
never leaves empty room in its cell that it could fill.
"""

from typing import Optional, Tuple, Union

from interactive_pipe.graphical import view_geometry
from interactive_pipe.graphical.view_geometry import FIT_TOLERANCE, MAX_ZOOM, MIN_ZOOM, CellContent, CellLayout

__all__ = ["ViewState", "VIEW_MODES", "ZOOM_STEP", "MIN_ZOOM", "MAX_ZOOM", "FIT_TOLERANCE", "CellContent"]

VIEW_MODES = ("fit", "1:1")
ZOOM_STEP = 1.25

Size = Tuple[float, float]
# (width, height) of a plain image, or a CellContent (heatmap with a colorbar / axes)
Content = Union[Size, CellContent]


def _content(size: Content) -> CellContent:
    if isinstance(size, CellContent):
        return size
    return CellContent.plain(size[0], size[1])


class ViewState:
    """absolute: False -> zoom multiplies each cell's fit scale; True -> zoom is
    screen pixels per image pixel. center: normalized image coordinates of the
    point displayed at the middle of each cell. native_cells: in the "1:1"
    family the cells also take the native size of their image (the viewport
    grows to it, ``actual_size="window"``); otherwise they keep their fitted
    size and the images show at 100% inside them."""

    def __init__(self, native_cells: bool = False) -> None:
        self.native_cells = native_cells
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

    @property
    def native_layout(self) -> bool:
        """The cells are laid out at the native size of their image (1:1 resizing the viewport)."""
        return self.absolute and self.native_cells

    def reset(self) -> None:
        self.set_mode("fit")

    def set_state(self, zoom: float, center: Tuple[float, float]) -> None:
        self.zoom = float(min(max(zoom, MIN_ZOOM), MAX_ZOOM))
        self.center = (float(center[0]), float(center[1]))

    # --- geometry (box = displayed cell size, size = image size or CellContent, in pixels) ---
    @staticmethod
    def fit_scale(box: Size, size: Content) -> float:
        return view_geometry.fit_scale(box, (size[0], size[1]))

    def layout(self, box: Size, size: Content) -> CellLayout:
        """Where the image (and a colorbar strip) is drawn in the box (view_geometry.cell_layout)."""
        return view_geometry.cell_layout(box, _content(size), self.zoom, self.absolute, self.center)

    def scale(self, box: Size, size: Content) -> float:
        """Screen pixels per image pixel (of the map, not of a colorbar)."""
        return self.layout(box, size).scale

    def min_zoom(self, box: Size, size: Content) -> float:
        """Smallest zoom: the image fits the box (or stays at its current base
        scale when that is already smaller, e.g. a small image at 1:1)."""
        return view_geometry.min_zoom(box, _content(size), self.absolute)

    def image_rect(self, box: Size, size: Content) -> Tuple[float, float, float, float]:
        """(x, y, width, height) of the drawn image (without a colorbar strip,
        which stays fixed) in box coordinates; centered along an axis where it fits."""
        return self.layout(box, size).main

    def zoom_by(self, factor: float, box: Size, size: Content, anchor: Optional[Tuple[float, float]] = None) -> None:
        """Zoom by `factor` keeping the image point under `anchor` (box
        coordinates, default: box center) in place."""
        if size[0] <= 0 or size[1] <= 0:
            self.set_state(self.zoom * factor, self.center)
            return
        zoom, center = view_geometry.zoom_center(
            box, _content(size), self.zoom, self.absolute, self.center, factor, anchor
        )
        self.set_state(zoom, center)

    def pan_by(self, dx: float, dy: float, box: Size, size: Content) -> None:
        """Move the image by (dx, dy) screen pixels."""
        if size[0] <= 0 or size[1] <= 0:
            return
        self.set_state(
            self.zoom, view_geometry.pan_center(box, _content(size), self.zoom, self.absolute, self.center, dx, dy)
        )
