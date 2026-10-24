from __future__ import annotations

import logging
from copy import copy, deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Callable, List, Optional, Tuple, Union

from interactive_pipe.core.filter import FilterCore

if TYPE_CHECKING:
    from interactive_pipe.headless.panel import Panel


class Control:
    """Binds a GUI widget to a filter keyword argument.

    The widget type is inferred from the type of ``value_default`` and the
    presence of ``value_range``:

    - ``bool`` -> checkbox (``value_range`` must be None)
    - ``int`` / ``float`` with a 2-element ``value_range`` -> slider
    - ``int`` / ``float`` without ``value_range`` -> free numeric parameter
    - ``str`` with a list of choices as ``value_range`` -> dropdown
    - ``str`` without ``value_range`` -> free text prompt

    Args:
        value_default: Initial value; its type selects the widget
            (int, float, bool or str).
        value_range: ``[min, max]`` for numeric sliders, or the list of
            choices for a string dropdown. Must be None for bool.
        name: Label displayed next to the widget. Auto-generated if omitted.
        step: Slider increment. Defaults to 1 for int sliders and 1/100 of
            the range for float sliders.
        filter_to_connect: Filter to connect immediately (requires
            ``parameter_name_to_connect``). Usually left to the
            ``@interactive`` decorator.
        parameter_name_to_connect: Keyword argument of the connected filter.
        icons: Icon image paths (one per choice) for string dropdowns.
        group: ``Panel`` instance or panel name used to group controls;
            same-named string groups share one panel across filters.
        tooltip: Hover text displayed on the widget.

    Example:
        ```python
        @interactive(
            gain=Control(1.0, [0.0, 3.0]),  # float slider
            flip=Control(False),  # checkbox
            mode=Control("dark", ["dark", "light"]),  # dropdown
        )
        def my_filter(img, gain=1.0, flip=False, mode="dark"):
            ...
        ```
    """

    counter = 0
    _registry = {}  # Global registry to store controls for each function
    # Process-wide by design: same-named string groups share one Panel across filters
    _panel_cache = {}

    @staticmethod
    def registry_key(func: Callable) -> str:
        # Keyed by module + qualname so same-named functions in different
        # modules do not collide. functools.wraps preserves both, so the key
        # is identical for a decorated function and its wrapper.
        return f"{func.__module__}.{func.__qualname__}"

    @classmethod
    def register(cls, func, param_name, control_instance):
        cls._registry.setdefault(cls.registry_key(func), {})[param_name] = control_instance

    @classmethod
    def get_controls(cls, func):
        if not isinstance(func, Callable):
            raise TypeError(f"get_controls expects the function object, got {type(func)}")
        return cls._registry.get(cls.registry_key(func), {})

    def __init__(
        self,
        value_default: Union[int, float, bool, str],
        value_range: Optional[List[Union[int, float, str]]] = None,
        name: Optional[str] = None,
        step: Optional[Union[int, float]] = None,
        filter_to_connect: Optional[FilterCore] = None,
        parameter_name_to_connect: Optional[str] = None,
        icons: Optional[List] = None,
        group: Optional[Union[str, "Panel"]] = None,
        tooltip: Optional[str] = None,
    ) -> None:
        self.value_default = value_default
        self._type = None
        self._auto_named = False
        self.step = step
        self.tooltip = tooltip

        # Convert string to Panel for backward compatibility
        # Use cached Panel if same string name was used before
        if isinstance(group, str):
            from interactive_pipe.headless.panel import Panel

            if group not in Control._panel_cache:
                Control._panel_cache[group] = Panel(name=group)
            self.panel = Control._panel_cache[group]
        else:
            self.panel = group

        if isinstance(value_default, bool):
            self._type = bool
            self.step = 1
            if value_range is not None:
                raise ValueError("value_range must be None for bool type")
        elif isinstance(value_default, (float, int)):
            if value_range is None:  # free range parameter!
                self._type = int if isinstance(value_default, int) else float
            else:
                if not isinstance(value_range, (list, tuple)):
                    raise TypeError(f"value_range must be a list or tuple, got {type(value_range)}")
                if len(value_range) != 2:
                    raise ValueError(f"value_range must have exactly 2 elements, got {len(value_range)}")
                for choice in value_range:
                    if not isinstance(choice, (float, int)):
                        raise TypeError(f"value_range elements must be int or float, got {type(choice)}")
                if (
                    isinstance(value_default, int)
                    and isinstance(value_range[0], int)
                    and isinstance(value_range[1], int)
                ):
                    if self.step is None:
                        self.step = 1
                    self._type = int
                else:
                    self._type = float
                    if self.step is None:
                        # Type narrowing: we know value_range contains numeric values here
                        self.step = (value_range[1] - value_range[0]) / 100.0  # type: ignore
                if not (value_range[0] <= value_default <= value_range[1]):  # type: ignore
                    raise ValueError(f"value_default {value_default} must be within value_range {value_range}")
        elif isinstance(value_default, str):
            # similar to an enum
            if value_range is None:
                logging.debug("string prompt only - no range")
                self._type = str
            else:
                if not value_range:
                    raise ValueError("value_range cannot be empty for string type")
                if not isinstance(value_range, (list, tuple)):
                    raise TypeError(f"value_range must be a list or tuple, got {type(value_range)}")
                for choice in value_range:
                    if not isinstance(choice, str):
                        raise TypeError(f"value_range elements must be strings, got {type(choice)}")
                if value_default not in value_range:
                    raise ValueError(f"{value_default} must be in {value_range}")
                self._type = str
                if self.step is None:
                    self.step = 1
        else:
            raise TypeError(f"Wrong value type: {type(value_default)}, expected int/float/bool/str")
        self.value_range = value_range

        # init current value
        self.value = value_default
        self.icons = icons
        if self.icons is not None:
            for icon in self.icons:
                if isinstance(icon, str):
                    icon = Path(icon)
                if not icon.exists():
                    raise FileNotFoundError(f"Icon file not found: {icon}")
        if name is None:
            self._auto_named = True
            self.name = f"parameter {Control.counter}"
        else:
            self.name = name
        if not isinstance(self.name, str):
            raise TypeError(f"name must be a string, got {type(self.name)}")
        Control.counter += 1
        if filter_to_connect is not None:
            if parameter_name_to_connect is None:
                raise ValueError("parameter_name_to_connect is required when filter_to_connect is provided")
            self.connect_filter(filter_to_connect, parameter_name_to_connect)
        else:
            self.update_param_func = None

        self.parameter_name_to_connect = parameter_name_to_connect
        self.filter_to_connect = filter_to_connect

        # Register with panel if provided
        if self.panel is not None:
            self.panel._register_control(self)

    def check_value(self, value):
        if isinstance(value, int) and self._type is float:
            value = float(value)
        elif isinstance(value, float) and self._type is int:
            # Convert float to int (e.g., from matplotlib sliders that return floats)
            value = int(round(value))
        if self._type is not None and not isinstance(value, self._type):
            raise TypeError(f"Expected {self._type}, got {type(value)}")
        if isinstance(value, (float, int)) and self.value_range is not None:
            return max(self.value_range[0], min(value, self.value_range[1]))  # type: ignore
        elif self._type is str and self.value_range is not None:
            if value not in self.value_range:
                raise ValueError(f"{value} must be in {self.value_range}")
            return value
        else:
            return value

    def __repr__(self) -> str:
        if self._type in [float, int]:
            if self.value_range:
                return (
                    f"{self.name} | {self.value} - range {self.value_range} "
                    f"default = {self.value_default} type: {self._type} - step={self.step}"
                )
            else:
                return (
                    f"{self.name} | {self.value} - RANGELESS - default = {self.value_default} "
                    f"type: {self._type} - step={self.step}"
                )
        elif self._type is bool:
            return f"{self.name} | Bool {self.value} - default {self.value_default}"
        elif self._type is str:
            return (
                f"{self.name} | {self.value} - choices {self.value_range} default = {self.value_default} "
                f"type: {self._type} - step={self.step}"
            )
        else:
            raise NotImplementedError

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value=None):
        self._value = deepcopy(self.check_value(value) if value is not None else self.value_default)

    def reset(self):
        self.value = None

    def update(self, new_value):
        # Plug button
        self.value = new_value
        if self.update_param_func is not None:
            self.update_param_func(self.value)

    def _clone_unconnected(self, name: str) -> "Control":
        """Shallow clone for a repeated filter instance: same value spec,
        panel and widget type, but a fresh name, the default value and no
        filter connection (the pipeline connects it to the repeat)."""
        clone = copy(self)
        clone.name = name
        clone.filter_to_connect = None
        clone.parameter_name_to_connect = None
        clone.update_param_func = None
        clone.reset()
        if clone.panel is not None:
            clone.panel._register_control(clone)
        return clone

    def connect_parameter(self, update_param_func: Callable):
        self.update_param_func = update_param_func

    def connect_filter(self, filt: FilterCore, parameter_name):
        def update_param_func(val):
            logging.debug(f"update filter {filt.name} - param {parameter_name} - value {val}")
            filt.values = {parameter_name: val}

        self.update_param_func = update_param_func
        self.parameter_name_to_connect = parameter_name
        self.filter_to_connect = filt


class CircularControl(Control):
    """Circular (dial) variant of a numeric slider.

    Behaves like a numeric ``Control`` but is rendered as a rotary dial.
    With ``modulo=True`` the value wraps around at the ``value_range``
    bounds instead of saturating (useful for angles).
    """

    def __init__(
        self,
        value_default: Union[int, float],
        value_range: Optional[List[Union[int, float]]] = None,
        modulo: bool = True,
        name: Optional[str] = None,
        step: Optional[Union[int, float]] = None,
        filter_to_connect: Optional[FilterCore] = None,
        parameter_name_to_connect: Optional[str] = None,
        group: Optional[Union[str, Panel]] = None,
        tooltip: Optional[str] = None,
    ) -> None:
        super().__init__(
            value_default=value_default,
            value_range=value_range,  # type: ignore
            name=name,
            step=step,
            filter_to_connect=filter_to_connect,
            parameter_name_to_connect=parameter_name_to_connect,
            icons=None,
            group=group,
            tooltip=tooltip,
        )
        self.modulo = modulo

    def __repr__(self) -> str:
        return super().__repr__() + f"| modulo:{self.modulo}"


def range_pair(ctrl: "Control") -> Tuple[Union[int, float], Union[int, float]]:
    """Return the (lo, hi) value of a RangeControl as a typed pair.

    Widgets receive a plain Control reference; this helper validates and
    narrows the value for them instead of unpacking an untyped `.value`.
    """
    value = ctrl.value
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise TypeError(f"{ctrl.name}: expected a (lo, hi) pair, got {value!r}")
    return (value[0], value[1])


class RangeControl(Control):
    """Two-handle (min / max) slider bound to a ``(lo, hi)`` keyword argument.

    The filter receives a tuple ``(lo, hi)`` with ``lo <= hi``, both within
    ``value_range``. The element type (int or float) is inferred from
    ``value_default`` and ``value_range``: all ints give an int range slider,
    anything else a float one.

    Invalid defaults raise ``ValueError``; later updates (GUI, tuning files)
    are sanitized instead: the bounds are swapped if needed and clamped into
    ``value_range``. Values round-trip through json/yaml tuning files as a
    2-element list.

    Args:
        value_default: Initial ``(lo, hi)`` (tuple or list).
        value_range: ``[min, max]`` allowed for both handles.
        name: Label displayed next to the widget. Auto-generated if omitted.
        step: Slider increment. Defaults to 1 for int and 1/100 of the range
            for float.
        group: ``Panel`` instance or panel name used to group controls.
        tooltip: Hover text displayed on the widget.

    Example:
        ```python
        @interactive(window=RangeControl((0.2, 0.8), [0.0, 1.0]))
        def crop(img, window=(0.2, 0.8)):
            lo, hi = window
            ...
        ```
    """

    _range_ready = False

    def __init__(
        self,
        value_default: Union[Tuple[Union[int, float], Union[int, float]], List[Union[int, float]]],
        value_range: List[Union[int, float]],
        step: Optional[Union[int, float]] = None,
        name: Optional[str] = None,
        tooltip: Optional[str] = None,
        group: Optional[Union[str, Panel]] = None,
        filter_to_connect: Optional[FilterCore] = None,
        parameter_name_to_connect: Optional[str] = None,
    ) -> None:
        bounds = self._validate_pair(value_range, "value_range")
        default = self._validate_pair(value_default, "value_default")
        if bounds[0] >= bounds[1]:
            raise ValueError(f"value_range {value_range} must satisfy min < max")
        if default[0] > default[1]:
            raise ValueError(f"value_default {value_default} must satisfy lo <= hi")
        if not (bounds[0] <= default[0] and default[1] <= bounds[1]):
            raise ValueError(f"value_default {value_default} must be within value_range {value_range}")
        is_int = all(isinstance(v, int) for v in (*default, *bounds))
        elem_type = int if is_int else float
        super().__init__(
            value_default=elem_type(default[0]),
            value_range=[elem_type(bounds[0]), elem_type(bounds[1])],
            name=name,
            step=step,
            filter_to_connect=None,
            parameter_name_to_connect=None,
            icons=None,
            group=group,
            tooltip=tooltip,
        )
        self.value_default = (elem_type(default[0]), elem_type(default[1]))
        self._range_ready = True
        self.value = None  # reset to the (lo, hi) default
        if filter_to_connect is not None:
            if parameter_name_to_connect is None:
                raise ValueError("parameter_name_to_connect is required when filter_to_connect is provided")
            self.connect_filter(filter_to_connect, parameter_name_to_connect)

    @staticmethod
    def _validate_pair(pair, label: str) -> Tuple[Union[int, float], Union[int, float]]:
        if not isinstance(pair, (list, tuple)):
            raise TypeError(f"{label} must be a 2-element list or tuple, got {type(pair)}")
        if len(pair) != 2:
            raise ValueError(f"{label} must have exactly 2 elements, got {len(pair)}")
        for element in pair:
            if isinstance(element, bool) or not isinstance(element, (int, float)):
                raise TypeError(f"{label} elements must be int or float, got {type(element)}")
        return pair[0], pair[1]

    def _coerce_element(self, element):
        if isinstance(element, bool):
            raise TypeError(f"Range bounds must be numbers, got {type(element)}")
        try:
            number = float(element)  # also accepts numpy scalars from widgets
        except (TypeError, ValueError):
            raise TypeError(f"Range bounds must be numbers, got {type(element)}") from None
        return int(round(number)) if self._type is int else number

    def check_value(self, value):
        """Sanitize a new ``(lo, hi)``: sort the bounds and clamp them into ``value_range``.

        Accepts a tuple, a list (json/yaml tuning files), any 2-element
        sequence (numpy array from matplotlib) or a ``"lo, hi"`` string
        (text-based frontends).
        """
        if not self._range_ready:
            # scalar bootstrap value set by Control.__init__
            return super().check_value(value)
        if isinstance(value, str):
            parts = value.strip().strip("()[]").split(",")
            if len(parts) != 2:
                raise ValueError(f"Cannot parse {value!r} as 'lo, hi'")
            try:
                value = [float(part) for part in parts]
            except ValueError:
                raise ValueError(f"Cannot parse {value!r} as 'lo, hi'") from None
        try:
            elements = list(value)
        except TypeError:
            raise TypeError(f"RangeControl value must be a (lo, hi) pair, got {type(value)}") from None
        if len(elements) != 2:
            raise ValueError(f"RangeControl value must have exactly 2 elements, got {len(elements)}")
        lo, hi = sorted(self._coerce_element(element) for element in elements)
        value_min, value_max = self.value_range  # type: ignore[misc]
        lo = max(value_min, min(lo, value_max))
        hi = max(value_min, min(hi, value_max))
        return (lo, hi)

    def __repr__(self) -> str:
        return (
            f"{self.name} | {self.value} - RANGE in {self.value_range} "
            f"default = {self.value_default} type: {self._type} - step={self.step}"
        )


class TextPrompt(Control):
    """Free-text entry box bound to a string keyword argument.

    Unlike a string ``Control`` with a ``value_range`` (a dropdown of fixed
    choices), a ``TextPrompt`` accepts arbitrary text typed by the user.
    """

    def __init__(
        self,
        value_default: str,
        name: Optional[str] = None,
        filter_to_connect: Optional[FilterCore] = None,
        parameter_name_to_connect: Optional[str] = None,
        group: Optional[Union[str, Panel]] = None,
        tooltip: Optional[str] = None,
    ) -> None:
        super().__init__(
            value_default=value_default,
            value_range=None,
            name=name,
            step=None,
            filter_to_connect=filter_to_connect,
            parameter_name_to_connect=parameter_name_to_connect,
            icons=None,
            group=group,
            tooltip=tooltip,
        )

    def __repr__(self) -> str:
        return super().__repr__()


class TimeControl(Control):
    """
    Auto-incrementing time control for animations.

    Starts at 0.0 and increments automatically. Press 'p' to pause/resume.

    Note:
        Only supported on the Qt and Dear PyGui backends. Falls back to a regular slider on other backends
        (tooltip/group params are only relevant in that fallback case).

    Args:
        update_interval_ms: Interval between updates in milliseconds (default: 1000).
        pause_resume_key: Key to pause/resume (default: "p").

    Example:
        ```python
        @interactive(time=TimeControl(update_interval_ms=50))
        def animate(time=0.0):
            return time
        ```
    """

    def __init__(
        self,
        name: Optional[str] = None,
        update_interval_ms: int = 1000,
        pause_resume_key: str = "p",
        filter_to_connect: Optional[FilterCore] = None,
        parameter_name_to_connect: Optional[str] = None,
        group: Optional[Union[str, Panel]] = None,
        tooltip: Optional[str] = None,
    ) -> None:
        """Time control. Start at 0.0. Time can be paused/resumed"""
        super().__init__(
            value_default=0.0,
            value_range=[0.0, 3600.0],
            name=name,
            step=None,
            filter_to_connect=filter_to_connect,
            parameter_name_to_connect=parameter_name_to_connect,
            icons=None,
            group=group,
            tooltip=tooltip,
        )
        self.update_interval_ms = update_interval_ms
        self.pause_resume_key = pause_resume_key

    def __repr__(self) -> str:
        return super().__repr__()
