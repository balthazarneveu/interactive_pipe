"""Mouse input in the GUI backends: slider fallback, target cells, gestures, overlays.

Shared by every backend so each one only converts its own events to image
fractions and draws the overlay with its own primitives:

- ``controls_for_backend``: a backend without gestures (the default of
  ``InteractivePipeGUI.pointer_gestures``) gets one slider per coordinate
  instead of each ``PointControl`` / ``RegionControl``;
- ``PointerTargets``: which displayed cell receives the gestures of each
  control (``on=`` name, else the first image output) and the data area of
  that cell (heatmaps drawn with a colorbar map back to their data pixels);
- ``Gesture``: press / move / release in image fractions -> a click (sets the
  nearest point) or a shift-drag (sets the nearest region).
"""

import logging
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple, Union

import numpy as np

from interactive_pipe.graphical.display import display_data, display_kind, heatmap_geometry
from interactive_pipe.headless.pointer import PointControl, PointerControl, RegionControl, pointer_controls

# a press released within this many screen pixels is a click, not a drag
CLICK_TOLERANCE_PX = 3.0

Cell = Tuple[int, int]


def handles(gestures: Union[bool, Iterable[str]], ctrl: PointerControl) -> bool:
    """Whether a backend declaring ``pointer_gestures=gestures`` drives ``ctrl`` with the mouse."""
    if isinstance(gestures, bool):
        return gestures
    return ctrl.kind in tuple(gestures)


def controls_for_backend(controls: Iterable[Any], gestures: Union[bool, Iterable[str]]) -> List[Any]:
    """The controls a backend builds widgets for.

    Without gestures each point / region control is replaced by its
    coordinate sliders (``x``, ``y`` / ``x0``, ``y0``, ``x1``, ``y1``), in the
    control list and in its panel. With gestures the control itself stays
    (the backend binds the mouse and draws no widget for it). ``gestures`` is
    a bool or the kinds the backend handles (``("point",)``).
    """
    result: List[Any] = []
    for ctrl in controls:
        if not isinstance(ctrl, PointerControl):
            result.append(ctrl)
            continue
        sliders = ctrl.fallback_controls()
        shown = [ctrl] if handles(gestures, ctrl) else list(sliders)
        if ctrl.panel is not None:
            _place_in_panel(ctrl.panel._controls, [ctrl, *sliders], shown)
        result += shown
    return result


def _place_in_panel(panel_controls: List[Any], family: List[Any], shown: List[Any]) -> None:
    """Replace whichever of ``family`` the panel lists by ``shown``, at the same place."""
    positions = [index for index, item in enumerate(panel_controls) if any(item is member for member in family)]
    if not positions:
        return
    first = positions[0]
    panel_controls[:] = [item for item in panel_controls if not any(item is member for member in family)]
    panel_controls[first:first] = shown


# ---------------------------------------------------------------------------
# Target cells
# ---------------------------------------------------------------------------


def _output_names(outputs: Any) -> List[List[Any]]:
    if not outputs:
        return []
    if not isinstance(outputs[0], list):
        return [list(outputs)]
    return [list(row) for row in outputs]


class PointerTargets:
    """Resolve, for one frame, the cell each pointer control is attached to.

    Args:
        controls: the pipeline controls (non-pointer ones are ignored).
        output_names: grid of output names currently displayed
            (``pipeline.outputs``).
        contents: grid of raw outputs of the last run (same shape).
        styles: ``{(row, col): style}`` ``layout.style`` of each cell.
    """

    def __init__(
        self,
        controls: Iterable[Any],
        output_names: Any,
        contents: Any,
        styles: Optional[Dict[Cell, dict]] = None,
    ) -> None:
        self.controls = pointer_controls(controls)
        self.names = _output_names(output_names)
        self.contents = _output_names(contents)
        self.styles = styles or {}
        self.cells: Dict[int, Cell] = {}  # id(control) -> cell
        self._warned: set = set()
        first_image = self._first_image_cell()
        for ctrl in self.controls:
            cell = self._named_cell(ctrl.on) if ctrl.on is not None else first_image
            if cell is None:
                continue
            kind = display_kind(self._content(cell))
            if kind == "figure":
                _warn_once(
                    f"{type(ctrl).__name__} '{ctrl.name}': on={ctrl.on!r} is a matplotlib figure output. "
                    "Clicks on figures are not supported: point the control at an image output"
                )
                continue
            if kind != "image":
                continue
            self.cells[id(ctrl)] = cell

    def _content(self, cell: Cell) -> Any:
        row, col = cell
        try:
            return self.contents[row][col]
        except (IndexError, TypeError):
            return None

    def _named_cell(self, name: str) -> Optional[Cell]:
        for row, names in enumerate(self.names):
            for col, item in enumerate(names):
                if item == name:
                    return (row, col)
        return None

    def _first_image_cell(self) -> Optional[Cell]:
        for row, names in enumerate(self.names):
            for col, _ in enumerate(names):
                if display_kind(self._content((row, col))) == "image":
                    return (row, col)
        return None

    def controls_at(self, cell: Cell) -> List[PointerControl]:
        return [ctrl for ctrl in self.controls if self.cells.get(id(ctrl)) == cell]

    def cell_of(self, ctrl: PointerControl) -> Optional[Cell]:
        return self.cells.get(id(ctrl))

    def data_size(self, cell: Cell, shown_shape: Optional[Sequence[int]] = None) -> Optional[Sequence[float]]:
        """(width, height) of the data area of ``cell`` in displayed pixels.

        The displayed image of a heatmap with a colorbar is the (upscaled) map
        followed by the colorbar strip: only the map receives gestures. With
        axes the map starts after margins: a ``DataArea`` (width, height, x0,
        y0) is returned, which ``to_fraction`` / ``overlay_items`` take.
        """
        content = display_data(self._content(cell))
        geometry = heatmap_geometry(content, self.styles.get(cell))
        if geometry is not None:
            # (width, height, x0, y0): axes margins put the map's corner at (x0, y0)
            return DataArea(
                float(geometry.width * geometry.upscale),
                float(geometry.height * geometry.upscale),
                float(geometry.x0),
                float(geometry.y0),
            )
        if shown_shape is not None:
            return float(shown_shape[1]), float(shown_shape[0])
        shape = np.shape(content)
        if len(shape) < 2:
            return None
        return float(shape[1]), float(shape[0])


_WARNED: set = set()  # messages already logged (process-wide)


def _warn_once(message: str) -> None:
    if message not in _WARNED:
        _WARNED.add(message)
        logging.warning(message)


class DataArea(NamedTuple):
    """Data area of a cell in displayed pixels: its size and top-left corner."""

    width: float
    height: float
    x0: float = 0.0
    y0: float = 0.0


def _area(data_size: Sequence[float]) -> DataArea:
    return DataArea(*data_size)


def to_fraction(u: float, v: float, data_size: Sequence[float]) -> Tuple[float, float]:
    """Displayed pixel coordinates (continuous, origin at the top-left corner
    of the image) -> fractions of the data area (not clamped).

    ``data_size``: (width, height), or a ``DataArea`` (width, height, x0, y0)."""
    area = _area(data_size)
    return (u - area.x0) / area.width, (v - area.y0) / area.height


def inside(fraction: Tuple[float, float]) -> bool:
    return 0.0 <= fraction[0] <= 1.0 and 0.0 <= fraction[1] <= 1.0


def clamp(fraction: Tuple[float, float]) -> Tuple[float, float]:
    return (min(1.0, max(0.0, fraction[0])), min(1.0, max(0.0, fraction[1])))


# ---------------------------------------------------------------------------
# Gestures
# ---------------------------------------------------------------------------


def nearest(controls: Sequence[PointerControl], fraction: Tuple[float, float]) -> Optional[PointerControl]:
    """The control whose marker (point, or region centre) is the closest to ``fraction``."""
    if not controls:
        return None

    def distance(ctrl: PointerControl) -> float:
        value: Any = ctrl.value
        if isinstance(ctrl, RegionControl):
            x0, y0, x1, y1 = value
            center = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        else:
            center = value
        return (center[0] - fraction[0]) ** 2 + (center[1] - fraction[1]) ** 2

    return min(controls, key=distance)


class Gesture:
    """One mouse gesture on a cell: press, move(s), release.

    ``press`` returns False when nothing on this cell listens (the backend
    then keeps its own behaviour, e.g. panning). A region gesture (shift held
    at press time) updates the region live on every move; a point gesture
    sets the point on release if the mouse moved less than
    ``CLICK_TOLERANCE_PX`` screen pixels (a longer drag is left to panning).
    """

    def __init__(self) -> None:
        self.cell: Optional[Cell] = None
        self.start: Optional[Tuple[float, float]] = None
        self.start_screen: Optional[Tuple[float, float]] = None
        self.region: Optional[RegionControl] = None
        self.moved = False

    @property
    def active(self) -> bool:
        return self.cell is not None

    @property
    def drawing_region(self) -> bool:
        return self.region is not None

    def press(
        self,
        targets: PointerTargets,
        cell: Cell,
        fraction: Tuple[float, float],
        screen: Tuple[float, float],
        shift: bool,
    ) -> bool:
        self.cancel()
        controls = targets.controls_at(cell)
        if not controls or not inside(fraction):
            return False
        if shift:
            regions = [ctrl for ctrl in controls if isinstance(ctrl, RegionControl)]
            if not regions:
                return False
            self.region = nearest(regions, fraction)  # type: ignore[assignment]
        elif not any(isinstance(ctrl, PointControl) for ctrl in controls):
            return False
        self.cell, self.start, self.start_screen, self.moved = cell, fraction, screen, False
        return True

    def move(self, fraction: Tuple[float, float], screen: Tuple[float, float]) -> Optional[PointerControl]:
        """Returns the control to update now (a region being drawn), else None."""
        if not self.active or self.start_screen is None or self.start is None:
            return None
        if abs(screen[0] - self.start_screen[0]) + abs(screen[1] - self.start_screen[1]) > CLICK_TOLERANCE_PX:
            self.moved = True
        if self.region is not None and self.moved:
            end = clamp(fraction)
            self.region.value = (self.start[0], self.start[1], end[0], end[1])
            return self.region
        return None

    def release(
        self, targets: PointerTargets, fraction: Tuple[float, float], screen: Tuple[float, float]
    ) -> Optional[PointerControl]:
        """Returns the control whose value changed (None: nothing to do)."""
        if not self.active or self.start is None:
            return None
        changed = self.move(fraction, screen)
        cell, start, moved, region = self.cell, self.start, self.moved, self.region
        self.cancel()
        if region is not None or moved or cell is None:
            return changed  # a region drawn (or a click with shift: nothing), or a pan
        points = [ctrl for ctrl in targets.controls_at(cell) if isinstance(ctrl, PointControl)]
        point = nearest(points, start)
        if point is None:
            return None
        point.value = clamp(start)
        return point

    def cancel(self) -> None:
        self.cell = self.start = self.start_screen = None
        self.region = None
        self.moved = False


# ---------------------------------------------------------------------------
# Overlay geometry (in displayed pixels of the cell's image)
# ---------------------------------------------------------------------------


def overlay_items(targets: PointerTargets, cell: Cell, data_size: Sequence[float]) -> List[Tuple[str, Any, str]]:
    """Marks to draw over ``cell``: ``("region", (u0, v0, u1, v1), label)``
    then ``("point", (u, v), label)``, in displayed pixel coordinates."""
    width, height, ox, oy = _area(data_size)
    regions: List[Tuple[str, Any, str]] = []
    points: List[Tuple[str, Any, str]] = []
    for ctrl in targets.controls_at(cell):
        value: Any = ctrl.value
        if isinstance(ctrl, RegionControl):
            x0, y0, x1, y1 = value
            regions.append(
                ("region", (ox + x0 * width, oy + y0 * height, ox + x1 * width, oy + y1 * height), ctrl.name)
            )
        else:
            x, y = value
            points.append(("point", (ox + x * width, oy + y * height), ctrl.name))
    return regions + points  # points drawn on top


POINT_COLOR = (255, 64, 160)  # magenta-pink, readable on gray images and most colormaps
REGION_COLOR = (64, 224, 255)  # cyan


def help_lines(controls: Iterable[Any]) -> List[str]:
    """Help (F1) lines of the mouse gestures, for a backend with gestures."""
    lines = []
    for ctrl in pointer_controls(controls):
        where = f"'{ctrl.on}'" if ctrl.on is not None else "the first image"
        if isinstance(ctrl, RegionControl):
            lines.append(f"[shift+drag] on {where} : draw {ctrl.name}")
        else:
            lines.append(f"[click] on {where} : set {ctrl.name}")
    return lines
