from typing import List, Optional, Union, Callable
from interactive_pipe.headless.pipeline import HeadlessPipeline
from copy import deepcopy
from abc import abstractmethod
from interactive_pipe.core.filter import FilterCore

class Control():
    counter = 0
    def __init__(self, value_default: Union[int, float, bool,str], value_range: List[Union[int, float, str]]=None, name=None, step=None, filter_to_connect: Optional[FilterCore] = None, parameter_name_to_connect: Optional[str] = None) -> None:
        self.value_default = value_default
        self._type = None
        if isinstance(value_default, float) or isinstance(value_default, int):
            if value_range is None: # free range parameter!
                self._type = int if isinstance(value_default, int) else float
            else:
                assert isinstance(value_range, list) or isinstance(value_range, tuple)
                assert len(value_range) == 2
                for choice in value_range:
                    assert isinstance(choice, float) or isinstance(choice, int)
                if isinstance(value_default, int) and isinstance(value_range[0], int) and isinstance(value_range[1], int):
                    self.step = 1
                    self._type = int
                else:
                    self._type = float
                assert value_default >= value_range[0] and value_default <= value_range[1]
        elif isinstance(value_default, bool):
            self._type = bool
            assert value_range is None
        elif isinstance(value_default, str):
            # similar to an enum
            assert value_range
            assert isinstance(value_range, list) or isinstance(value_range, tuple)
            for choice in value_range:
                assert isinstance(choice, str)
            assert value_default in value_range, f"{value_default} shall be in {value_range}"
            self._type = str
        else:
            raise TypeError("Wrong value type")
        self.value_range = value_range
        self.step = step
        # init current value
        self.value = value_default
        if name is None:
            self.name = f"parameter {Control.counter}"
        else:
            self.name = name
        Control.counter+=1
        if filter_to_connect is not None:
            assert parameter_name_to_connect is not None
            self.connect_filter(filter_to_connect, parameter_name_to_connect)
        else:
            self.update_param_func = None
        

    def check_value(self, value):
        if isinstance(value, int) and self._type == float:
            value = float(value)
        assert isinstance(value, self._type)
        if isinstance(value, float) or isinstance(value, int) and self.value_range:
            return max(self.value_range[0], min(value, self.value_range[1]))
        elif self._type == str:
            assert value in self.value_range, f"{value} shall be in {self.value_range}"
            return value
    def __repr__(self) -> str:
        if self._type in [float, int]:
            if self.value_range:
                return f"{self.value} - range {self.value_range} default = {self.value_default} type: {self._type}"
            else:
                return f"{self.value} - RANGELESS - default = {self.value_default} type: {self._type}"
        elif self._type == bool:
            return f"Bool {self.value} - default {self.value_default}"
        elif self._type == str:
            return  f"{self.value} - choices {self.value_range} default = {self.value_default} type: {self._type}"
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
            print(f"update filter {filter.name} - param {parameter_name} - value {val}")
            filter.values = {parameter_name: val}
        self.update_param_func = update_param_func