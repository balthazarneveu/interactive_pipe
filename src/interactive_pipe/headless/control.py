from typing import List, Optional, Union, Callable, Tuple
from copy import deepcopy
from abc import abstractmethod
from interactive_pipe.core.filter import FilterCore
from pathlib import Path
import logging


class Control:
    counter = 0
    _registry = {}  # Global registry to store controls for each function

    @classmethod
    def register(cls, func_name, param_name, control_instance):
        cls._registry.setdefault(func_name, {})[param_name] = control_instance

    @classmethod
    def get_controls(cls, func):
        if isinstance(func, Callable):
            func_name = func.__name__
        else:
            func_name = func
        return cls._registry.get(func_name, {})

    def __init__(
        self,
        value_default: Union[int, float, bool, str],
        value_range: Optional[List[Union[int, float, str]]] = None,
        name: Optional[str] = None,
        step: Optional[Union[int, float]] = None,
        filter_to_connect: Optional[FilterCore] = None,
        parameter_name_to_connect: Optional[str] = None,
        icons: Optional[List] = None,
        parent_control: Optional["RangeSlider"] = None,
    ) -> None:
        self.value_default = value_default
        self._type = None
        self._auto_named = False
        self.step = step
        if isinstance(value_default, bool):
            self._type = bool
            self.step = 1
            if value_range is not None:
                raise ValueError("value_range must be None for bool type")
        elif isinstance(value_default, float) or isinstance(value_default, int):
            if value_range is None:  # free range parameter!
                self._type = int if isinstance(value_default, int) else float
            else:
                if not isinstance(value_range, (list, tuple)):
                    raise TypeError(
                        f"value_range must be a list or tuple, got {type(value_range)}"
                    )
                if len(value_range) != 2:
                    raise ValueError(
                        f"value_range must have exactly 2 elements, got {len(value_range)}"
                    )
                for choice in value_range:
                    if not isinstance(choice, (float, int)):
                        raise TypeError(
                            f"value_range elements must be int or float, got {type(choice)}"
                        )
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
                        self.step = (value_range[1] - value_range[0]) / 100.0
                if not (value_range[0] <= value_default <= value_range[1]):
                    raise ValueError(
                        f"value_default {value_default} must be within value_range {value_range}"
                    )
        elif isinstance(value_default, str):
            # similar to an enum
            if value_range is None:
                logging.debug("string prompt only - no range")
                self._type = str
            else:
                if not value_range:
                    raise ValueError("value_range cannot be empty for string type")
                if not isinstance(value_range, (list, tuple)):
                    raise TypeError(
                        f"value_range must be a list or tuple, got {type(value_range)}"
                    )
                for choice in value_range:
                    if not isinstance(choice, str):
                        raise TypeError(
                            f"value_range elements must be strings, got {type(choice)}"
                        )
                if value_default not in value_range:
                    raise ValueError(f"{value_default} must be in {value_range}")
                self._type = str
                if self.step is None:
                    step = 1
        else:
            raise TypeError(
                f"Wrong value type: {type(value_default)}, expected int/float/bool/str"
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
                raise ValueError(
                    "parameter_name_to_connect is required when filter_to_connect is provided"
                )
            self.connect_filter(filter_to_connect, parameter_name_to_connect)
        else:
            self.update_param_func = None

        self.parameter_name_to_connect = parameter_name_to_connect
        self.filter_to_connect = filter_to_connect
        self.parent_control = parent_control
        if parent_control is not None:
            if not isinstance(parent_control, RangeSlider):
                raise TypeError(
                    f"parent_control must be a RangeSlider instance, got {type(parent_control)}"
                )
            # Validate that value_default and value_range match parent
            if value_range != parent_control.value_range:
                raise ValueError(
                    f"Control value_range {value_range} must match parent RangeSlider "
                    f"value_range {parent_control.value_range}"
                )

    def check_value(self, value):
        if isinstance(value, int) and self._type == float:
            value = float(value)
        if not isinstance(value, self._type):
            raise TypeError(f"Expected {self._type}, got {type(value)}")
        if isinstance(value, float) or isinstance(value, int) and self.value_range:
            return max(self.value_range[0], min(value, self.value_range[1]))
        elif self._type == str and self.value_range is not None:
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
        elif self._type == bool:
            return f"{self.name} | Bool {self.value} - default {self.value_default}"
        elif self._type == str:
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
        self._value = deepcopy(
            self.check_value(value) if value is not None else self.value_default
        )

    def reset(self):
        self.value = None

    @abstractmethod
    def update(self, new_value):
        # Plug button
        self.value = new_value
        if self.update_param_func is not None:
            self.update_param_func(self.value)

    def connect_parameter(self, update_param_func: Callable):
        self.update_param_func = update_param_func

    def connect_filter(self, filter: FilterCore, parameter_name):
        def update_param_func(val):
            logging.info(
                f"update filter {filter.name} - param {parameter_name} - value {val}"
            )
            filter.values = {parameter_name: val}

        self.update_param_func = update_param_func
        self.parameter_name_to_connect = parameter_name
        self.filter_to_connect = filter


class CircularControl(Control):
    """
    Replace a slider by a circular slider
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
    ) -> None:
        super().__init__(
            value_default=value_default,
            value_range=value_range,
            name=name,
            step=step,
            filter_to_connect=filter_to_connect,
            parameter_name_to_connect=parameter_name_to_connect,
            icons=None,
        )
        self.modulo = modulo

    def __repr__(self) -> str:
        return super().__repr__() + f"| modulo:{self.modulo}"


class TextPrompt(Control):
    def __init__(
        self,
        value_default: str,
        name: Optional[str] = None,
        filter_to_connect: Optional[FilterCore] = None,
        parameter_name_to_connect: Optional[str] = None,
    ) -> None:
        """Text box"""
        super().__init__(
            value_default=value_default,
            value_range=None,
            name=name,
            step=None,
            filter_to_connect=filter_to_connect,
            parameter_name_to_connect=parameter_name_to_connect,
            icons=None,
        )

    def __repr__(self) -> str:
        return super().__repr__()


class TimeControl(Control):
    def __init__(
        self,
        name: Optional[str] = None,
        update_interval_ms: int = 1000,
        pause_resume_key: str = "p",
        filter_to_connect: Optional[FilterCore] = None,
        parameter_name_to_connect: Optional[str] = None,
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
        )
        self.update_interval_ms = update_interval_ms
        self.pause_resume_key = pause_resume_key

    def __repr__(self) -> str:
        return super().__repr__()


class RangeSlider:
    """A dual-handle slider that controls two parameters simultaneously.

    Usage:
        my_range_slider = RangeSlider([-1, 1], default=(-0.5, 0.5), name="Brightness")

        @interactive(
            param_min=Control(-0.5, [-1., 1.], parent_control=my_range_slider),
            param_max=Control(0.5, [-1., 1.], parent_control=my_range_slider),
        )
        def my_filter(img, param_min=-0.5, param_max=0.5):
            # Both are regular floats, slider ensures param_min <= param_max
            ...
    """

    def __init__(
        self,
        value_range: List[Union[int, float]],
        default: Optional[Tuple[Union[int, float], Union[int, float]]] = None,
        name: Optional[str] = None,
        step: Optional[Union[int, float]] = None,
    ):
        if not isinstance(value_range, (list, tuple)):
            raise TypeError(
                f"value_range must be a list or tuple, got {type(value_range)}"
            )
        if len(value_range) != 2:
            raise ValueError(
                f"value_range must have exactly 2 elements [min, max], got {len(value_range)}"
            )
        for val in value_range:
            if not isinstance(val, (int, float)):
                raise TypeError(
                    f"value_range elements must be int or float, got {type(val)}"
                )
        if value_range[0] >= value_range[1]:
            raise ValueError(
                f"value_range[0] must be < value_range[1], got {value_range}"
            )

        self.value_range = list(value_range)

        # Default to full range if not specified
        if default is None:
            default = (value_range[0], value_range[1])
        else:
            if not isinstance(default, (list, tuple)):
                raise TypeError(f"default must be a list or tuple, got {type(default)}")
            if len(default) != 2:
                raise ValueError(
                    f"default must have exactly 2 elements (left, right), got {len(default)}"
                )
            for val in default:
                if not isinstance(val, (int, float)):
                    raise TypeError(
                        f"default elements must be int or float, got {type(val)}"
                    )
            if not (value_range[0] <= default[0] <= value_range[1]):
                raise ValueError(
                    f"default[0] {default[0]} must be within value_range {value_range}"
                )
            if not (value_range[0] <= default[1] <= value_range[1]):
                raise ValueError(
                    f"default[1] {default[1]} must be within value_range {value_range}"
                )
            if default[0] > default[1]:
                raise ValueError(
                    f"default[0] {default[0]} must be <= default[1] {default[1]}"
                )

        self.default = tuple(default)

        # Determine type (int or float) based on inputs
        all_int = all(isinstance(v, int) for v in value_range + list(default))
        self._type = int if all_int else float

        # Current values (updated by GUI)
        self._left_value = self.default[0]
        self._right_value = self.default[1]

        # Step size
        if step is None:
            if self._type == int:
                self.step = 1
            else:
                self.step = (value_range[1] - value_range[0]) / 100.0
        else:
            self.step = step

        # Name
        if name is None:
            self._auto_named = True
            self.name = f"range_slider {Control.counter}"
            Control.counter += 1
        else:
            self._auto_named = False
            self.name = name
            Control.counter += 1

        if not isinstance(self.name, str):
            raise TypeError(f"name must be a string, got {type(self.name)}")

    def set_values(self, left_value: Union[int, float], right_value: Union[int, float]):
        """Update both handle values (called by GUI backends)."""
        # Clamp values to range
        self._left_value = max(
            self.value_range[0], min(left_value, self.value_range[1])
        )
        self._right_value = max(
            self.value_range[0], min(right_value, self.value_range[1])
        )
        # Ensure left <= right
        if self._left_value > self._right_value:
            self._left_value = self._right_value

    def get_values(self) -> Tuple[Union[int, float], Union[int, float]]:
        """Get current handle values."""
        return (self._left_value, self._right_value)

    def __repr__(self) -> str:
        return (
            f"{self.name} | RangeSlider - range {self.value_range} "
            f"default = {self.default} type: {self._type} - step={self.step}"
        )
