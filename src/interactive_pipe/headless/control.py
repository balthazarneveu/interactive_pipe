from __future__ import annotations

import logging
import math
from copy import copy, deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Tuple, Union

import numpy as np

from interactive_pipe.core.filter import FilterCore

if TYPE_CHECKING:
    from interactive_pipe.headless.panel import Panel


SCALES = ("linear", "log")


def nice_step(span: float) -> float:
    """Default float slider step: 1, 2 or 5 x 10^k, the closest (as a ratio) to ``span / 100``,
    so that slider values read 0.05 rather than 0.0195."""
    if not span > 0:
        return span / 100.0
    target = span / 100.0
    exponent = math.floor(math.log10(target))
    candidates = [float(f"{mantissa}e{power}") for power in (exponent, exponent + 1) for mantissa in (1, 2, 5)]
    return min(candidates, key=lambda candidate: abs(math.log(candidate / target)))


def _clean(value: float) -> float:
    """Remove float noise from ``min + k * step`` (0.25000000000000006 -> 0.25)."""
    return float(f"{value:.12g}")


def _control_label(name: Optional[str]) -> str:
    """``"control 'gain': "`` when the control has a name yet, else ``""``."""
    return f"control '{name}': " if isinstance(name, str) else ""


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
        step: Slider increment. Defaults to 1 for int sliders; for float
            sliders 1, 2 or 5 x 10^k close to 1/100 of the range (0.02 for
            [0, 3], 1 for [2, 100]).
        filter_to_connect: Filter to connect immediately (requires
            ``parameter_name_to_connect``). Usually left to the
            ``@interactive`` decorator.
        parameter_name_to_connect: Keyword argument of the connected filter.
        icons: Icon image paths (one per choice) for string dropdowns.
        group: ``Panel`` instance or panel name used to group controls;
            same-named string groups share one panel across filters.
        tooltip: Hover text displayed on the widget.
        scale: ``"linear"`` (default) or ``"log"``: a log slider moves
            evenly over decades (``Control(1e-2, [1e-4, 1e-1], scale="log")``);
            its value, label, sweeps (``steps=`` are geometric) and tuning files
            hold the real value, rounded to 3 significant digits by the widget.
            Needs a positive range; no ``step``.

    Example:
        ```python
        @interactive(
            gain=Control(1.0, [0.0, 3.0]),  # float slider
            lr=Control(1e-2, [1e-4, 1e-1], scale="log"),  # log slider
            flip=Control(False),  # checkbox
            mode=Control("dark", ["dark", "light"]),  # dropdown
        )
        def my_filter(img, gain=1.0, flip=False, mode="dark"):
            ...
        ```
    """

    counter = 0
    _registry = {}  # controls of callables that cannot hold attributes (see register)
    # set on some instances only (read with __dict__.get): the declared control a
    # pipeline clone comes from, the key sharing one widget, the parameter an
    # auto-named control was named after
    _origin: "Control"
    _share_key: Any
    _named_after_parameter: str
    # Process-wide by design: same-named string groups share one Panel across filters
    _panel_cache = {}

    #: attribute of the (unwrapped) filter function holding its registered controls
    CONTROLS_ATTRIBUTE = "__interactive_pipe_controls__"

    @staticmethod
    def registry_key(func: Callable) -> str:
        """Readable ``module.qualname`` of a filter function (used in messages and
        as the fallback key for callables that cannot hold attributes)."""
        qualname = getattr(func, "__qualname__", None)
        if qualname is None:
            # functools.partial and other callable objects: no declaration of their own
            return f"{getattr(func, '__module__', type(func).__module__)}.<{type(func).__name__} at {id(func):#x}>"
        return f"{func.__module__}.{qualname}"

    @staticmethod
    def _declaration_owner(func: Callable) -> Any:
        """The function object that owns the controls: the innermost function
        behind ``functools.wraps`` wrappers (the decorated function and its
        wrapper share one set of controls)."""
        import inspect

        try:
            return inspect.unwrap(func)
        except ValueError:  # pragma: no cover - wrapper loop
            return func

    @classmethod
    def register(cls, func, param_name, control_instance):
        """Register `control_instance` for `param_name` of `func`.

        Controls live on the function object itself, so two functions with the
        same ``module.qualname`` (two ``__main__`` scripts run in one
        interpreter, filters made by a factory) never share controls, and the
        controls go away with the function.
        """
        owner = cls._declaration_owner(func)
        controls = owner.__dict__.get(cls.CONTROLS_ATTRIBUTE) if hasattr(owner, "__dict__") else None
        if controls is None:
            controls = {}
            try:
                setattr(owner, cls.CONTROLS_ATTRIBUTE, controls)
            except (AttributeError, TypeError):  # no attributes (builtins): keyed by name
                controls = cls._registry.setdefault(cls.registry_key(func), {})
        controls[param_name] = control_instance

    @classmethod
    def get_controls(cls, func):
        if not isinstance(func, Callable):
            raise TypeError(f"get_controls expects the function object, got {type(func)}")
        owner = cls._declaration_owner(func)
        controls = owner.__dict__.get(cls.CONTROLS_ATTRIBUTE) if hasattr(owner, "__dict__") else None
        if controls is not None:
            return controls
        return cls._registry.get(cls.registry_key(func), {})

    @classmethod
    def clear_controls(cls, func) -> None:
        """Forget the controls registered for `func` (re-decoration starts clean)."""
        owner = cls._declaration_owner(func)
        if hasattr(owner, "__dict__"):
            owner.__dict__.pop(cls.CONTROLS_ATTRIBUTE, None)
        cls._registry.pop(cls.registry_key(func), None)

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
        scale: str = "linear",
    ) -> None:
        self.value_default = value_default
        self._type = None
        self._auto_named = False
        self.step = step
        self.tooltip = tooltip
        if scale not in SCALES:
            raise ValueError(f"{_control_label(name)}scale must be 'linear' or 'log', got {scale!r}")
        self.scale = scale

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
                    if self.step is None and scale == "linear":
                        # Type narrowing: we know value_range contains numeric values here
                        self.step = nice_step(value_range[1] - value_range[0])  # type: ignore
                if value_range[0] > value_range[1]:  # type: ignore[operator]
                    # min == max stays allowed: an image selector (0, [0, len(images) - 1]) on one image
                    raise ValueError(
                        f"value_range {list(value_range)} must satisfy min <= max "
                        f"(did you mean [{value_range[1]}, {value_range[0]}]?)"
                    )
                if not (value_range[0] <= value_default <= value_range[1]):  # type: ignore
                    low, high = value_range  # type: ignore[misc]
                    raise ValueError(
                        f"{_control_label(name)}the default {value_default} is outside the range "
                        f"{list(value_range)}: choose a default between {low} and {high}, or widen the range"
                    )
                if scale == "log":
                    self._validate_log_scale(value_default, value_range, step, name)
                self._validate_step(value_range)
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
                    raise ValueError(
                        f"{_control_label(name)}the default {value_default!r} is not one of the choices "
                        f"{list(value_range)}"
                    )
                self._type = str
                if self.step is None:
                    self.step = 1
        else:
            raise TypeError(
                f"{_control_label(name)}wrong default type {type(value_default).__name__} {value_default!r}, "
                "expected int, float, bool or str"
            )
        if scale == "log" and (self._type is not float or value_range is None):
            raise ValueError(
                f"{_control_label(name)}scale='log' needs a float slider: Control(1e-2, [1e-4, 1e-1], scale='log') "
                "(use float bounds or default)"
            )
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

    @staticmethod
    def _validate_log_scale(value_default, value_range, step, name) -> None:
        if step is not None:
            raise ValueError(
                f"{_control_label(name)}a log slider has no step (it moves evenly over decades): remove step="
            )
        if not value_range[0] > 0:
            raise ValueError(
                f"{_control_label(name)}a log slider needs a positive range, got {list(value_range)}: "
                f"start it above 0, e.g. [{value_range[1] / 1000:g}, {value_range[1]:g}]"
            )

    @property
    def is_log(self) -> bool:
        return self.__dict__.get("scale", "linear") == "log"

    def to_position(self, value) -> float:
        """Slider position in [0, 1] of a value (log scale: evenly over decades)."""
        low, high = float(self.value_range[0]), float(self.value_range[1])  # type: ignore[index,arg-type]
        if high == low:
            return 0.0
        value = min(max(float(value), low), high)
        if self.is_log:
            return (math.log10(value) - math.log10(low)) / (math.log10(high) - math.log10(low))
        return (value - low) / (high - low)

    def from_position(self, position: float):
        """Value at a slider position in [0, 1]: snapped to the step (linear scale) or
        rounded to 3 significant digits (log scale), within the range."""
        low, high = float(self.value_range[0]), float(self.value_range[1])  # type: ignore[index,arg-type]
        position = min(max(float(position), 0.0), 1.0)
        if self.is_log:
            value = 10 ** (math.log10(low) + position * (math.log10(high) - math.log10(low)))
            value = min(max(float(f"{value:.3g}"), low), high)
        else:
            value = self.snap(low + position * (high - low))
        return value

    def snap(self, value: float) -> float:
        """A linear slider value on the step grid (min + k * step), without float noise."""
        if self.is_log or not self.step or self.value_range is None:
            return value
        low, high = self.value_range[0], self.value_range[1]
        snapped = low + round((value - low) / self.step) * self.step  # type: ignore[operator]
        return min(max(_clean(snapped), low), high)  # type: ignore[type-var]

    def _validate_step(self, value_range) -> None:
        """A slider step must be a positive number no larger than the range."""
        step = self.step
        if step is None:
            return
        if isinstance(step, bool) or not isinstance(step, (int, float)):
            raise TypeError(f"step must be a number, got {step!r}")
        span = value_range[1] - value_range[0]
        if step <= 0:
            raise ValueError(f"step {step!r} must be > 0 (slider over {list(value_range)})")
        if span > 0 and step > span:
            raise ValueError(
                f"step {step!r} is larger than the range {list(value_range)}: the slider could not move. "
                f"Use a step <= {span}"
            )

    def check_value(self, value):
        if isinstance(value, np.generic):
            value = value.item()  # numpy scalars (np.float32(2.0), np.int64(3), np.str_...) are plain values
        if isinstance(value, bool) and self._type in (int, float):
            raise TypeError(f"control '{self.name}' expects a number, got {value!r}")
        if isinstance(value, int) and self._type is float:
            value = float(value)
        elif isinstance(value, float) and self._type is int:
            # Convert float to int (e.g., from matplotlib sliders that return floats)
            value = int(round(value))
        if self._type is not None and not isinstance(value, self._type):
            raise TypeError(
                f"control '{self.name}' expects {self._type.__name__}, got {type(value).__name__} {value!r}"
            )
        if isinstance(value, (float, int)) and self.value_range is not None:
            clamped = max(self.value_range[0], min(value, self.value_range[1]))  # type: ignore
            self._warn_clamped(value, clamped)
            return clamped
        elif self._type is str and self.value_range is not None:
            if value not in self.value_range:
                raise ValueError(f"control '{self.name}': {value!r} is not one of the choices {list(self.value_range)}")
            return value
        else:
            return value

    def _warn_clamped(self, value, clamped) -> None:
        """Out-of-range values are clamped (tuning files and sessions rely on it), but never silently."""
        if clamped == value or self.value_range is None or self._clamp_reported_by_caller:
            return
        low, high = self.value_range[0], self.value_range[1]
        try:
            # float noise from slider widgets (min + k * step) is not worth a warning
            tolerance = 1e-9 * max(1.0, abs(float(high) - float(low)))  # type: ignore[arg-type]
            values = value if isinstance(value, (list, tuple)) else [value]
            references = clamped if isinstance(clamped, (list, tuple)) else [clamped]
            if all(abs(float(v) - float(r)) <= tolerance for v, r in zip(values, references)):
                return
        except (TypeError, ValueError):
            pass
        logging.warning(
            f"Control '{self.name}': value {value!r} is outside its range [{low}, {high}], clamped to {clamped!r}"
        )

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

    #: True while a caller that reports the clamping itself sets the value
    _clamp_reported_by_caller = False

    def _set_value_caller_reports_clamp(self, value: Any) -> None:
        """Set ``value`` without the control's own clamp warning: the caller
        (``snapshot`` / ``sweep`` overrides) words it for its user, once."""
        self._clamp_reported_by_caller = True
        try:
            self.value = value
        finally:
            del self._clamp_reported_by_caller

    def update(self, new_value):
        # Plug button
        self.value = new_value
        if self.update_param_func is not None:
            self.update_param_func(self.value)

    def _clone_unconnected(self, name: str, keep_value: bool = False) -> "Control":
        """Shallow clone for one pipeline (or one repeated filter instance): same
        value spec, panel and widget type, but a fresh name, the default value
        (unless ``keep_value``: a pipeline starts from the declared control's
        current value) and no filter connection (the pipeline connects it).

        The clone is not added to its panel's ``_controls``: a GUI lists the
        controls of a panel among its own pipeline's controls
        (``Panel.controls_among``), so clones made by other pipelines never
        show up there (and are not kept alive by the panel)."""
        clone = copy(self)
        clone.name = name
        clone.filter_to_connect = None
        clone.parameter_name_to_connect = None
        clone._extra_targets = []
        clone.update_param_func = None
        clone._origin = self.origin
        if not keep_value:
            clone.reset()
        return clone

    @property
    def origin(self) -> "Control":
        """The declared control this one was cloned from (itself if it is a declaration)."""
        return self.__dict__.get("_origin") or self

    @property
    def share_key(self) -> int:
        """Controls with the same key are one widget within a pipeline.

        The declared object itself: the same ``Control`` passed to two
        ``@interactive`` decorators is shared. Per-function clones of an
        explicitly named annotation control carry the key of the annotation
        object (see ``helper/annotation_controls.py``).
        """
        key = self.__dict__.get("_share_key")
        return key if key is not None else id(self)

    @property
    def targets(self) -> List[Tuple[FilterCore, str]]:
        """``(filter, parameter)`` pairs this control drives in its pipeline.

        One pair for a control declared in one filter; several when the same
        control object is declared by several filters of the pipeline
        (``band = RangeControl(...)``; ``@interactive(band=band)`` twice).
        """
        if self.filter_to_connect is None or self.parameter_name_to_connect is None:
            return []
        return [(self.filter_to_connect, self.parameter_name_to_connect), *self.__dict__.get("_extra_targets", [])]

    def _add_target(self, filt: FilterCore, parameter_name: str) -> None:
        """Drive one more filter parameter (a control shared by several filters)."""
        if self.filter_to_connect is None:
            self.connect_filter(filt, parameter_name)
            return
        self.__dict__.setdefault("_extra_targets", []).append((filt, parameter_name))

    def _checked_default(self, value):
        """Validate a new default value for this control (no clamping: out of range raises)."""
        label = f"control '{self.name}'"
        if self._type is bool:
            if not isinstance(value, bool):
                raise TypeError(f"{label} is a checkbox: expected True or False, got {value!r}")
            return value
        if self._type in (int, float):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{label} expects a number, got {value!r}")
            if self._type is int:
                if isinstance(value, float) and not value.is_integer():
                    raise TypeError(f"{label} expects an integer, got {value!r}")
                value = int(value)
            else:
                value = float(value)
            if self.value_range is not None:
                low, high = self.value_range[0], self.value_range[1]
                if not (low <= value <= high):  # type: ignore[operator]
                    raise ValueError(f"{value!r} is outside the range [{low}, {high}] of {label}")
            return value
        if self._type is str:
            if not isinstance(value, str):
                raise TypeError(f"{label} expects a string, got {value!r}")
            if self.value_range is not None and value not in self.value_range:
                raise ValueError(f"{value!r} is not one of the choices {list(self.value_range)} of {label}")
            return value
        return self.check_value(value)

    def _clone_with_default(self, value_default, name: Optional[str] = None) -> "Control":
        """Unconnected clone whose default (and current value) is ``value_default``.

        Used for a filter instance given a literal keyword argument in the
        pipeline body: the registered control is shared by every pipeline using
        the filter, so it is never mutated.
        """
        checked = self._checked_default(value_default)
        clone = self._clone_unconnected(self.name if name is None else name)
        clone.value_default = checked
        clone.reset()
        return clone

    def connect_parameter(self, update_param_func: Callable):
        self.update_param_func = update_param_func

    def connect_filter(self, filt: FilterCore, parameter_name):
        """Drive ``parameter_name`` of ``filt`` (replaces any previous target)."""
        self.update_param_func = self._update_targets
        self.parameter_name_to_connect = parameter_name
        self.filter_to_connect = filt
        self._extra_targets = []

    def _update_targets(self, val) -> None:
        for filt, parameter_name in self.targets:
            logging.debug(f"update filter {filt.name} - param {parameter_name} - value {val}")
            filt.values = {parameter_name: val}


class MappedChoiceControl(Control):
    """Dropdown whose choices are string labels standing for arbitrary values.

    Built from ``Enum`` and non-string ``Literal`` annotations: the widget
    shows the labels (``Mode.DARK`` -> ``"DARK"``, ``Literal[3, 5]`` ->
    ``"3"``, ``"5"``) and the ``@interactive`` wrapper hands the filter the
    value itself (the enum member, the int). The control value stays the
    label, so every backend, tuning file and ``describe()`` sees a plain
    string dropdown. Setting the control accepts a label or a value.
    """

    def __init__(
        self,
        choices: dict,
        value_default: Any = None,
        name: Optional[str] = None,
        group: Optional[Union[str, "Panel"]] = None,
        tooltip: Optional[str] = None,
    ) -> None:
        if not choices:
            raise ValueError("a dropdown needs at least one choice")
        self._choice_values = dict(choices)
        label = next(iter(self._choice_values)) if value_default is None else self.to_label(value_default)
        super().__init__(label, list(self._choice_values), name=name, group=group, tooltip=tooltip)

    def to_label(self, value):
        """Label of a choice given as its value (or already as its label)."""
        for label, choice in self._choice_values.items():
            if choice is value:
                return label
        if type(value) is str and value in self._choice_values:
            return value
        for label, choice in self._choice_values.items():
            if type(choice) is type(value) and choice == value:
                return label
        return value  # not a choice: the base validation names the choices

    def to_value(self, value):
        """Value handed to the filter for a label (anything else is passed through)."""
        if type(value) is str and value in self._choice_values:
            return self._choice_values[value]
        return value

    def check_value(self, value):
        return super().check_value(self.to_label(value))

    def _checked_default(self, value):
        return super()._checked_default(self.to_label(value))


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
            raise ValueError(
                f"{_control_label(name)}the default {value_default} is outside the range {list(value_range)}"
            )
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
            raise TypeError(f"control '{self.name}': range bounds must be numbers, got {type(element).__name__}")
        try:
            number = float(element)  # also accepts numpy scalars from widgets
        except (TypeError, ValueError):
            raise TypeError(
                f"control '{self.name}': range bounds must be numbers, got {type(element).__name__}"
            ) from None
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
                raise ValueError(f"control '{self.name}': cannot parse {value!r} as 'lo, hi'")
            try:
                value = [float(part) for part in parts]
            except ValueError:
                raise ValueError(f"control '{self.name}': cannot parse {value!r} as 'lo, hi'") from None
        try:
            elements = list(value)
        except TypeError:
            raise TypeError(
                f"control '{self.name}' expects a (lo, hi) pair, got {type(value).__name__} {value!r}"
            ) from None
        if len(elements) != 2:
            raise ValueError(f"control '{self.name}' expects a (lo, hi) pair, got {len(elements)} elements")
        lo, hi = sorted(self._coerce_element(element) for element in elements)
        value_min, value_max = self.value_range  # type: ignore[misc]
        clamped = (max(value_min, min(lo, value_max)), max(value_min, min(hi, value_max)))
        self._warn_clamped((lo, hi), clamped)
        return clamped

    def _checked_default(self, value):
        lo, hi = self._validate_pair(value, f"default of control '{self.name}'")
        value_min, value_max = self.value_range  # type: ignore[misc]
        if lo > hi:
            raise ValueError(f"default {value!r} of control '{self.name}' must satisfy lo <= hi")
        if not (value_min <= lo and hi <= value_max):  # type: ignore[operator]
            raise ValueError(f"{value!r} is outside the range [{value_min}, {value_max}] of control '{self.name}'")
        return (self._type(lo), self._type(hi))  # type: ignore[misc]

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

    def _warn_clamped(self, value, clamped) -> None:
        # running past the end of the range is expected (the timer keeps ticking): stay quiet
        return

    def __repr__(self) -> str:
        return super().__repr__()
