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


class RangeSliderHandle:
    """Proxy object representing one handle of a RangeSlider.
    
    This is used to bind a single parameter to one handle of a dual-handle range slider.
    The decorator detects these handles and groups them by their parent RangeSlider.
    """

    def __init__(self, parent: "RangeSlider", side: str):
        if side not in ("left", "right"):
            raise ValueError(f"side must be 'left' or 'right', got {side}")
        self.parent = parent
        self.side = side  # 'left' or 'right'

    @property
    def value_default(self):
        """Get the default value for this handle."""
        idx = 0 if self.side == "left" else 1
        return self.parent.default[idx]

    def __repr__(self) -> str:
        return f"RangeSliderHandle(parent={self.parent.name}, side={self.side})"


class RangeSlider:
    """A dual-handle slider that controls two parameters simultaneously.
    
    Usage:
        brightness_range = RangeSlider([-1, 1], default=(-0.5, 0.5), name="Brightness")
        
        @interactive(
            param_min=brightness_range.left,   # Left handle -> param_min
            param_max=brightness_range.right   # Right handle -> param_max
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
                raise TypeError(
                    f"default must be a list or tuple, got {type(default)}"
                )
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
        all_int = all(
            isinstance(v, int) for v in value_range + list(default)
        )
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

        # Create handle proxies
        self._left_handle = RangeSliderHandle(self, "left")
        self._right_handle = RangeSliderHandle(self, "right")

    @property
    def left(self) -> RangeSliderHandle:
        """Get the left handle proxy."""
        return self._left_handle

    @property
    def right(self) -> RangeSliderHandle:
        """Get the right handle proxy."""
        return self._right_handle

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


class RangeSliderControlWrapper(Control):
    """Wrapper Control that represents a RangeSlider with parameter mappings.
    
    This is created automatically by the decorator when RangeSliderHandle objects
    are detected. It stores the RangeSlider and which parameters map to left/right handles.
    """

    def __init__(
        self,
        range_slider: RangeSlider,
        left_param_name: str,
        right_param_name: str,
    ):
        # Use the left handle's default value as the Control's default
        # The _type will be determined from the range_slider
        super().__init__(
            value_default=range_slider.default[0],
            value_range=range_slider.value_range,
            name=range_slider.name,
            step=range_slider.step,
        )
        self.range_slider = range_slider
        self.left_param_name = left_param_name
        self.right_param_name = right_param_name
        # Override _type to match range_slider
        self._type = range_slider._type
        # Override value_default to return tuple for range slider compatibility
        self._value_default_tuple = range_slider.default
        # Store filter connections for both parameters
        self._left_filter = None
        self._left_param_to_connect = None
        self._right_filter = None
        self._right_param_to_connect = None

    def connect_filter(self, filter: FilterCore, parameter_name):
        """Connect to filter - this will be called for both left and right params."""
        # Store both connections - the GUI will call this for the wrapper name
        # but we need to track which filter/param pairs to update
        # For now, we'll connect when the individual params are processed
        # This method may be called multiple times, so we need to handle that
        pass

    def connect_both_parameters(self, filter: FilterCore):
        """Connect both left and right parameters to the filter."""
        self._left_filter = filter
        self._left_param_to_connect = self.left_param_name
        self._right_filter = filter
        self._right_param_to_connect = self.right_param_name
        # Set initial values
        filter.values[self.left_param_name] = self.range_slider.default[0]
        filter.values[self.right_param_name] = self.range_slider.default[1]

    @property
    def value_default(self):
        """Return tuple for range slider compatibility with Gradio."""
        return self._value_default_tuple
    
    @value_default.setter
    def value_default(self, value):
        """Setter for value_default - store as tuple."""
        if isinstance(value, (tuple, list)) and len(value) == 2:
            self._value_default_tuple = tuple(value)
        else:
            # Fallback to single value (for compatibility)
            self._value_default_tuple = (value, value)
    
    def update(self, new_value):
        """Update from Gradio - new_value is a tuple/list [left, right]."""
        if isinstance(new_value, (tuple, list)) and len(new_value) == 2:
            left_value, right_value = new_value[0], new_value[1]
            self.update_both_values(left_value, right_value)
        else:
            # Fallback to single value (shouldn't happen for range slider)
            super().update(new_value)

    def update_both_values(self, left_value: Union[int, float], right_value: Union[int, float]):
        """Update both parameter values in the connected filter."""
        self.range_slider.set_values(left_value, right_value)
        # Update the Control's value property to the tuple for compatibility
        self._value = (left_value, right_value)
        if self._left_filter is not None:
            self._left_filter.values[self._left_param_to_connect] = left_value
        if self._right_filter is not None:
            self._right_filter.values[self._right_param_to_connect] = right_value
        # Also update the individual control values so decorator can access them
        if hasattr(self, "_left_control"):
            self._left_control.value = left_value
        if hasattr(self, "_right_control"):
            self._right_control.value = right_value
        # Also call update_param_func if set (for compatibility)
        if self.update_param_func is not None:
            # Call with a tuple to indicate both values changed
            self.update_param_func((left_value, right_value))

    def __repr__(self) -> str:
        return (
            f"{self.name} | RangeSliderControlWrapper - "
            f"left={self.left_param_name}, right={self.right_param_name}, "
            f"range={self.value_range}"
        )
