"""Mouse-driven controls: a clicked point and a dragged region on an output image.

``PointControl`` and ``RegionControl`` are ordinary controls whose value is a
tuple of fractions of the image size, in ``[0, 1]``:

- a point is ``(x, y)``, a region ``(x0, y0, x1, y1)`` with ``x0 <= x1`` and
  ``y0 <= y1`` (a region given the other way round is reordered);
- ``(0, 0)`` is the top-left corner of the image, ``(1, 1)`` the bottom-right;
- fractions keep a tuning file valid when the resolution changes, and the value
  is meaningful before any image exists. ``to_pixels(value, img)`` converts to
  pixel indices inside a filter.

In a GUI that supports gestures, a click on the target output sets the point
and a shift-drag draws the region; the window draws the marker itself.
Elsewhere (and in any backend that does not implement gestures), the control is
shown as sliders: ``x``, ``y`` (point) or ``x0``, ``y0``, ``x1``, ``y1``
(region). Headless (``pipe(img, seed=(0.2, 0.4))``, ``snapshot``, ``sweep``,
tuning files) it is just a parameter.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, List, Optional, Sequence, Tuple, Union

import numpy as np

from interactive_pipe.core.filter import FilterCore
from interactive_pipe.headless.control import Control

if TYPE_CHECKING:
    from interactive_pipe.headless.panel import Panel

Point = Tuple[float, float]
Region = Tuple[float, float, float, float]

# float noise from widgets (e.g. 1.0000000002 after a coordinate round trip) is snapped, not rejected
_TOLERANCE = 1e-6


class PointerControl(Control):
    """Base class of ``PointControl`` and ``RegionControl`` (a tuple of fractions in [0, 1])."""

    kind = "pointer"
    axes: Tuple[str, ...] = ()
    _ready = False

    def __init__(
        self,
        value_default: Sequence[float],
        on: Optional[str] = None,
        name: Optional[str] = None,
        group: Optional[Union[str, "Panel"]] = None,
        tooltip: Optional[str] = None,
        filter_to_connect: Optional[FilterCore] = None,
        parameter_name_to_connect: Optional[str] = None,
    ) -> None:
        if on is not None and not isinstance(on, str):
            raise TypeError(f"on= must be the name of a pipeline output (a string), got {on!r}")
        # validated before Control.__init__ registers the control anywhere
        default = self._sanitize(value_default, label="value_default")
        super().__init__(
            value_default=0.0,  # scalar bootstrap, replaced below
            value_range=[0.0, 1.0],
            name=name,
            group=group,
            tooltip=tooltip,
        )
        self.on = on
        self._type = tuple  # unknown widget factories skip it instead of drawing a float slider
        self.step = None
        self.value_default = default
        self._ready = True
        self.value = None  # reset to the tuple default
        self._fallback: Optional[List["PointerAxisControl"]] = None
        if filter_to_connect is not None:
            if parameter_name_to_connect is None:
                raise ValueError("parameter_name_to_connect is required when filter_to_connect is provided")
            self.connect_filter(filter_to_connect, parameter_name_to_connect)

    # ------------------------------------------------------------------ values

    @classmethod
    def _sanitize(cls, value: Any, label: str = "value") -> tuple:
        """Validate a value: the right number of finite numbers in [0, 1]."""
        size = len(cls.axes)
        expected = "(x, y)" if size == 2 else "(x0, y0, x1, y1)"
        if isinstance(value, str):
            parts = value.strip().strip("()[]").split(",")
            try:
                value = [float(part) for part in parts]
            except ValueError:
                raise ValueError(f"{cls.__name__} {label}: cannot parse {value!r} as {expected}") from None
        if isinstance(value, np.ndarray):
            value = value.tolist()
        if not isinstance(value, (list, tuple)):
            raise TypeError(f"{cls.__name__} {label} must be {expected} as fractions of the image size, got {value!r}")
        if len(value) != size:
            raise ValueError(
                f"{cls.__name__} {label} must have {size} elements {expected}, got {len(value)}: {tuple(value)!r}"
            )
        numbers = []
        for axis, element in zip(cls.axes, value):
            if isinstance(element, np.generic):
                element = element.item()
            if isinstance(element, bool) or not isinstance(element, (int, float)):
                raise TypeError(f"{cls.__name__} {label}: {axis} must be a number, got {element!r}")
            number = float(element)
            if not math.isfinite(number) or number < -_TOLERANCE or number > 1.0 + _TOLERANCE:
                raise ValueError(
                    f"{cls.__name__} {label}: {axis}={element!r} is outside [0, 1]. Coordinates are fractions "
                    f"of the image size: use to_pixels(value, img) in the filter to get pixels"
                )
            numbers.append(min(1.0, max(0.0, number)))
        return cls._ordered(tuple(numbers))

    @staticmethod
    def _ordered(value: tuple) -> tuple:
        return value

    def check_value(self, value):
        if not self._ready:
            return super().check_value(value)  # scalar bootstrap of Control.__init__
        return self._sanitize(value, label=f"value of control '{self.name}'")

    def _checked_default(self, value):
        return self._sanitize(value, label=f"default of control '{self.name}'")

    def __repr__(self) -> str:
        on = "" if self.on is None else f" on {self.on!r}"
        return f"{self.name} | {self.kind} {self.value}{on} - default = {self.value_default}"

    # ------------------------------------------------------- slider fallback

    def fallback_controls(self) -> List["PointerAxisControl"]:
        """One float slider in [0, 1] per coordinate, editing this control.

        Used by every backend without mouse gestures (the default for a new
        backend): see ``graphical.pointer_input.controls_for_backend``.
        """
        if self._fallback is None:
            self._fallback = [PointerAxisControl(self, index) for index in range(len(self.axes))]
        return self._fallback

    def _clone_unconnected(self, name: str) -> "Control":
        clone = super()._clone_unconnected(name)
        clone._fallback = None  # type: ignore[attr-defined]
        return clone


class PointControl(PointerControl):
    """A point ``(x, y)`` set by a click on an output image.

    Coordinates are fractions of the image size in ``[0, 1]``, ``(0, 0)``
    being the top-left corner. Use ``to_pixels(point, img)`` in the filter to
    get the ``(col, row)`` pixel.

    Args:
        value_default: Initial ``(x, y)``.
        on: Name of the pipeline output that receives the clicks (default:
            the first image output).
        name: Label of the control. Auto-generated if omitted.
        group: ``Panel`` instance or panel name (used by the slider fallback).
        tooltip: Hover text of the slider fallback.

    Example:
        ```python
        @interactive(seed=PointControl((0.5, 0.5), on="img"))
        def row_profile(img, seed=(0.5, 0.5)):
            col, row = to_pixels(seed, img)
            return img[row]
        ```
    """

    kind = "point"
    axes = ("x", "y")


class RegionControl(PointerControl):
    """A rectangle ``(x0, y0, x1, y1)`` drawn by a shift-drag on an output image.

    Coordinates are fractions of the image size in ``[0, 1]``; a region given
    with ``x1 < x0`` (or ``y1 < y0``) is reordered. Use
    ``to_pixels(region, img)`` to get pixel bounds such that
    ``img[y0:y1, x0:x1]`` is the region (never empty).

    Args:
        value_default: Initial ``(x0, y0, x1, y1)``.
        on: Name of the pipeline output that receives the drags (default:
            the first image output).
        name: Label of the control. Auto-generated if omitted.
        group: ``Panel`` instance or panel name (used by the slider fallback).
        tooltip: Hover text of the slider fallback.

    Example:
        ```python
        @interactive(roi=RegionControl((0.25, 0.25, 0.75, 0.75), on="img"))
        def crop(img, roi=(0.25, 0.25, 0.75, 0.75)):
            x0, y0, x1, y1 = to_pixels(roi, img)
            return img[y0:y1, x0:x1]
        ```
    """

    kind = "region"
    axes = ("x0", "y0", "x1", "y1")

    @staticmethod
    def _ordered(value: tuple) -> tuple:
        x0, y0, x1, y1 = value
        return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


class PointerAxisControl(Control):
    """Float slider in [0, 1] for one coordinate of a point / region control.

    Holds no value of its own: reading and writing go through the parent
    control, so the sliders, the parent and the filter never disagree.
    """

    def __init__(self, parent: PointerControl, index: int) -> None:
        self.parent = parent
        self.index = index
        self._bound = False  # Control.__init__ assigns value: do not write the parent then
        super().__init__(
            value_default=float(parent.value_default[index]),
            value_range=[0.0, 1.0],
            name=f"{parent.name} {parent.axes[index]}",
            step=0.001,
            tooltip=parent.tooltip,
        )
        self.panel = parent.panel  # placed by controls_for_backend, not registered here
        self._bound = True

    @property
    def value_default(self):
        return float(self.parent.value_default[self.index])

    @value_default.setter
    def value_default(self, _value) -> None:
        pass  # always the parent's default

    @property
    def value(self):
        return float(self.parent.value[self.index])

    @value.setter
    def value(self, value=None) -> None:
        if not self._bound:
            return
        checked = self.value_default if value is None else self.check_value(value)
        coordinates = list(self.parent.value)
        coordinates[self.index] = checked
        if isinstance(self.parent, RegionControl):
            # dragging x0 past x1 pushes x1 along instead of swapping the sliders
            first, second = (self.index, self.index + 2) if self.index < 2 else (self.index - 2, self.index)
            if coordinates[first] > coordinates[second]:
                coordinates[second if self.index < 2 else first] = checked
        self.parent.value = tuple(coordinates)

    def update(self, new_value):
        self.value = new_value
        if self.parent.update_param_func is not None:
            self.parent.update_param_func(self.parent.value)


# ---------------------------------------------------------------------------
# Fractions <-> pixels
# ---------------------------------------------------------------------------


def _image_size(img: Any) -> Tuple[int, int]:
    """(height, width) of an array-like image, or of an explicit (height, width) shape."""
    if isinstance(img, tuple) and len(img) in (2, 3) and all(isinstance(v, (int, np.integer)) for v in img):
        shape = img
    else:
        data = getattr(img, "data", None)
        if not isinstance(img, np.ndarray) and isinstance(data, np.ndarray):
            img = data  # interactive_pipe.Image
        shape = getattr(img, "shape", None)
        if shape is None or len(shape) < 2:
            raise TypeError(f"to_pixels needs an image (array of shape (H, W[, C])) or a shape, got {type(img)}")
    height, width = int(shape[0]), int(shape[1])
    if height < 1 or width < 1:
        raise ValueError(f"to_pixels: empty image of shape {tuple(shape)}")
    return height, width


def to_pixels(value: Sequence[float], img: Any) -> Tuple[int, ...]:
    """Convert a point / region given as fractions to pixel indices of ``img``.

    - a point ``(x, y)`` gives ``(col, row)``, the pixel under it (clipped
      into the image): ``img[row, col]``;
    - a region ``(x0, y0, x1, y1)`` gives ``(x0, y0, x1, y1)`` in pixels with
      ``img[y0:y1, x0:x1]`` the region, at least one pixel wide and tall.

    ``img`` is an array of shape ``(H, W[, C])`` (or ``Image``), or the shape
    itself.

    Example:
        ```python
        col, row = to_pixels(seed, img)
        x0, y0, x1, y1 = to_pixels(roi, img)
        crop = img[y0:y1, x0:x1]
        ```
    """
    height, width = _image_size(img)
    if len(value) == 2:
        x, y = PointControl._sanitize(value)
        return (min(int(x * width), width - 1), min(int(y * height), height - 1))
    x0, y0, x1, y1 = RegionControl._sanitize(value)

    def bounds(low: float, high: float, size: int) -> Tuple[int, int]:
        start = min(int(round(low * size)), size - 1)
        stop = max(int(round(high * size)), start + 1)
        return start, min(stop, size)

    col0, col1 = bounds(x0, x1, width)
    row0, row1 = bounds(y0, y1, height)
    return (col0, row0, col1, row1)


def to_fractions(value: Sequence[float], img: Any) -> Tuple[float, ...]:
    """Inverse of ``to_pixels``: pixel coordinates of ``img`` to fractions.

    A point ``(col, row)`` maps to the centre of that pixel, a region
    ``(x0, y0, x1, y1)`` to its edges.
    """
    height, width = _image_size(img)
    if len(value) == 2:
        col, row = value
        return PointControl._sanitize(((col + 0.5) / width, (row + 0.5) / height))
    x0, y0, x1, y1 = value
    return RegionControl._sanitize((x0 / width, y0 / height, x1 / width, y1 / height))


# ---------------------------------------------------------------------------
# Target outputs
# ---------------------------------------------------------------------------


def _flat_names(outputs: Any) -> List[str]:
    if isinstance(outputs, str):
        return [outputs]
    if isinstance(outputs, (list, tuple)):
        return [name for item in outputs for name in _flat_names(item)]
    return []


def pointer_controls(controls: Any) -> List[PointerControl]:
    return [ctrl for ctrl in controls or [] if isinstance(ctrl, PointerControl)]


def check_targets(pipeline: Any) -> None:
    """Raise ``ValueError`` when a point / region control names (``on=``) an
    output that the pipeline does not produce, listing the available names."""
    controls = pointer_controls(getattr(pipeline, "controls", None))
    if not controls:
        return
    displayed = _flat_names(getattr(pipeline, "outputs", None))
    produced = list(displayed)
    for filt in getattr(pipeline, "filters", None) or []:
        produced += _flat_names(filt.outputs)  # layout.grid may show any of them
    produced += _flat_names(list(getattr(pipeline, "inputs_routing", None) or []))
    for ctrl in controls:
        if ctrl.on is not None and ctrl.on not in produced:
            where = f" of filter '{ctrl.filter_to_connect.name}'" if ctrl.filter_to_connect is not None else ""
            raise ValueError(
                f"{type(ctrl).__name__} '{ctrl.name}'{where}: on={ctrl.on!r} is not an output of pipeline "
                f"'{getattr(pipeline, 'name', '?')}'. Available outputs: {list(dict.fromkeys(displayed))}"
            )
