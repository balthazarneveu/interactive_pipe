import inspect
import logging
import sys
import time
import traceback
from copy import deepcopy
from typing import Callable, Dict, List, Optional, Tuple

from core.cache import CachedResults
from core.sliders import Slider

class PureFilter:
    def __init__(self, apply_fn: Optional[Callable] = None, name: Optional[str] = None, default_params: dict = {}):
        self.name = name if name else (
            self.__class__.__name__ if not apply_fn else apply_fn.__name__)
        if apply_fn is not None:
            self.apply = apply_fn
        self.__initialize_default_values() # initialize default values from .apply method
        self.values = deepcopy(default_params)

    @property
    def global_params(self):
        return self._global_params

    @global_params.setter
    def global_params(self, new_global_params: dict):
        """
        This is just a way to provide a context to each filter so they communicate globally
        and the pointer to the shared dictionary shall be shared at an upper level (pipeline)
        """
        assert isinstance(new_global_params, dict)
        self._global_params = new_global_params



    def check_apply_signature(self):
        if not hasattr(self, "__args_names") or not hasattr(self, "__kwargs_names"):
            self.__args_names, self.__kwargs_names = self.analyze_apply_fn_signature(
                self.apply)
        else:  # skip computing signature
            pass
    def __initialize_default_values(self):
        assert not hasattr(self, "_values")
        self.check_apply_signature()
        # print("INIT:",self.__kwargs_names)
        self._values = self.__kwargs_names
        if "global_params" in self.__kwargs_names.keys():
            self._values.pop("global_params")
    @property
    def values(self):
        return self._values

    @values.setter
    def values(self, new_values):
        assert isinstance(
            new_values, dict), f"{new_values} is not a dictionary"
        
        self._values = {**self._values, **new_values}

    def run(self, *imgs) -> list:
        # First we check if the keyword args of the apply function match with self.values
        assert isinstance(self.values, dict), f"{self.values}"
        self.check_apply_signature()
        for key, val in self.values.items():
            assert key in self.__kwargs_names.keys(
            ), f"{key} not in {self.__kwargs_names.keys()}"
        if "global_params" in self.__kwargs_names.keys():
            # special key to provide the context dictionary
            out = self.apply(
                *imgs, global_params=self.global_params, **self.values)
        else:
            out = self.apply(*imgs, **self.values)
        return out

    @staticmethod
    def analyze_apply_fn_signature(apply_fn: Callable) -> Tuple[dict, dict]:
        signature = inspect.signature(apply_fn)
        keyword_args = {
            k: v.default
            for k, v in signature.parameters.items()
            if v.default is not inspect.Parameter.empty
        }

        positional_args = [
            k
            for k, v in signature.parameters.items()
            if v.default is inspect.Parameter.empty
        ]
        return positional_args, keyword_args


class FilterCore(PureFilter):
    """PureFilter + cache + routing nodes defined (inputs & outputs fields)"""

    def __init__(self,
                 apply_fn: Callable = None,
                 name: Optional[str] = None,
                 default_params: dict = {},
                 inputs: List[int] = [0],
                 outputs: List[int] = [0],
                 cache=True,
                 ):
        super().__init__(apply_fn=apply_fn, name=name,
                         default_params=default_params)
        self.inputs = inputs
        self.outputs = outputs
        self.cache = cache
        self.reset_cache()

    def reset_cache(self):
        if self.cache:
            self.cache_mem = CachedResults(self.name)
        else:
            self.cache_mem = None

    def run(self, *imgs) -> list:
        # TODO: support routing mechanism based on List[int] or List[str | generic routing object]
        assert len(imgs) == len(
            self.inputs), "number of inputs shall match what's expected"
        if self.inputs is None:
            filter_in = ()
        else:
            filter_in = imgs
        out = super().run(*filter_in)
        if out is not None:
            assert len(out) >= len(
                self.outputs), "number of outputs shall be at least greater or equal to what's expected by the filter"
        assert isinstance(out, list)
        return out

    def __repr__(self) -> str:
        descr = "%s\n" % self.name
        if not (self.inputs == [0] and self.outputs == [0]):
            descr += "(" + (",".join(["%d" % it for it in self.inputs])) + ")"
            descr += "->" + \
                "(" + ",".join(["%d" % it for it in self.outputs]) + ")\n"
        descr += "\n"
        return descr