from typing import List, Optional, Union, Callable
from copy import deepcopy
from abc import abstractmethod
from interactive_pipe.core.filter import FilterCore
from pathlib import Path
import logging


class Control():
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

    def __init__(self, value_default: Union[int, float, bool, str], value_range: List[Union[int, float, str]] = None, name=None, step=None, filter_to_connect: Optional[FilterCore] = None, parameter_name_to_connect: Optional[str] = None, icons=None) -> None:
        self.value_default = value_default
        self._type = None
        self._auto_named = False
        self.step = step
        if isinstance(value_default, bool):
            self._type = bool
            self.step = 1
            assert value_range is None
        elif isinstance(value_default, float) or isinstance(value_default, int):
            if value_range is None:  # free range parameter!
                self._type = int if isinstance(value_default, int) else float
            else:
                assert isinstance(value_range, list) or isinstance(
                    value_range, tuple)
                assert len(value_range) == 2
                for choice in value_range:
                    assert isinstance(choice, float) or isinstance(choice, int)
                if isinstance(value_default, int) and isinstance(value_range[0], int) and isinstance(value_range[1], int):
                    if self.step is None:
                        self.step = 1
                    self._type = int
                else:
                    self._type = float
                    if self.step is None:
                        self.step = (value_range[1] - value_range[0])/100.
                assert value_default >= value_range[0] and value_default <= value_range[1]
        elif isinstance(value_default, str):
            # similar to an enum
            assert value_range
            assert isinstance(value_range, list) or isinstance(
                value_range, tuple)
            for choice in value_range:
                assert isinstance(choice, str)
            assert value_default in value_range, f"{value_default} shall be in {value_range}"
            self._type = str
            if self.step is None:
                step = 1
        else:
            raise TypeError("Wrong value type")
        self.value_range = value_range

        # init current value
        self.value = value_default
        self.icons = icons
        if self.icons is not None:
            for icon in self.icons:
                if isinstance(icon, str):
                    icon = Path(icon)
                assert icon.exists()
        if name is None:
            self._auto_named = True
            self.name = f"parameter {Control.counter}"
        else:
            self.name = name
        assert isinstance(self.name, str), f"{self.name} shall be a string"
        Control.counter += 1
        if filter_to_connect is not None:
            assert parameter_name_to_connect is not None
            self.connect_filter(filter_to_connect, parameter_name_to_connect)
        else:
            self.update_param_func = None

        self.parameter_name_to_connect = parameter_name_to_connect
        self.filter_to_connect = filter_to_connect

    def check_value(self, value):
        if isinstance(value, int) and self._type == float:
            value = float(value)
        assert isinstance(value, self._type), f"{type(value)} != {self._type}"
        if isinstance(value, float) or isinstance(value, int) and self.value_range:
            return max(self.value_range[0], min(value, self.value_range[1]))
        elif self._type == str:
            assert value in self.value_range, f"{value} shall be in {self.value_range}"
            return value
        else:
            return value

    def __repr__(self) -> str:
        if self._type in [float, int]:
            if self.value_range:
                return f"{self.name} | {self.value} - range {self.value_range} default = {self.value_default} type: {self._type} - step={self.step}"
            else:
                return f"{self.name} | {self.value} - RANGELESS - default = {self.value_default} type: {self._type} - step={self.step}"
        elif self._type == bool:
            return f"{self.name} | Bool {self.value} - default {self.value_default}"
        elif self._type == str:
            return f"{self.name} | {self.value} - choices {self.value_range} default = {self.value_default} type: {self._type} - step={self.step}"
        else:
            raise NotImplementedError

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value=None):
        self._value = deepcopy(self.check_value(
            value) if value is not None else self.value_default)

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
                f"update filter {filter.name} - param {parameter_name} - value {val}")
            filter.values = {parameter_name: val}
        self.update_param_func = update_param_func
        self.parameter_name_to_connect = parameter_name
        self.filter_to_connect = filter


class CircularControl(Control):
    """
    Replace a slider by a circular slider
    """

    def __init__(self, value_default: Union[int, float, bool, str], value_range: List[Union[int, float, str]] = None, modulo=True, name=None, step=None, filter_to_connect: Optional[FilterCore] = None, parameter_name_to_connect: Optional[str] = None) -> None:
        super().__init__(value_default=value_default, value_range=value_range, name=name, step=step,
                         filter_to_connect=filter_to_connect, parameter_name_to_connect=parameter_name_to_connect, icons=None)
        self.modulo = modulo

    def __repr__(self) -> str:
        return super().__repr__() + f"| modulo:{self.modulo}"
