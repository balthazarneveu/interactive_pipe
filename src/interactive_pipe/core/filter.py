import logging
from copy import deepcopy
from typing import Callable, List, Optional, Union, Tuple, Any

from interactive_pipe.core.cache import CachedResults
from interactive_pipe.core.signature import analyze_apply_fn_signature

EQUIVALENT_STATE_KEYS = ["global_params", "global_parameters", "global_state", "global_context", "context", "state"]


class PureFilter:
    def __init__(self, apply_fn: Optional[Callable] = None, name: Optional[str] = None, default_params: dict = {}):
        self.name = name if name else (
            self.__class__.__name__ if not apply_fn else apply_fn.__name__)
        if apply_fn is not None:
            self.apply = apply_fn
        self._global_params = {}
        self.__initialize_default_values()  # initialize default values from .apply method
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
            self.__args_names, self.__kwargs_names = analyze_apply_fn_signature(
                self.apply)
            self.signature = (self.__args_names, self.__kwargs_names)
        else:  # skip computing signature
            pass

    def __initialize_default_values(self):
        assert not hasattr(self, "_values")
        self.check_apply_signature()
        self._values = self.__kwargs_names
        for global_key in EQUIVALENT_STATE_KEYS:
            if global_key in self.__kwargs_names.keys():
                self._values.pop(global_key)

    @property
    def values(self):
        return self._values

    @values.setter
    def values(self, new_values):
        assert isinstance(
            new_values, dict), f"{new_values} is not a dictionary"
        self._values = {**self._values, **new_values}

    def run(self, *imgs) -> Tuple[Any]:
        # First we check if the keyword args of the apply function match with self.values
        assert isinstance(self.values, dict), f"{self.values}"
        self.check_apply_signature()
        for key, val in self.values.items():
            assert key in self.__kwargs_names.keys(
            ), f"{self.name} : {key} not in {self.__kwargs_names.keys()}"
        global_key_found = False
        for global_key in EQUIVALENT_STATE_KEYS:
            if global_key in self.__kwargs_names.keys():
                # special key to provide the context dictionary
                out = self.apply(
                    *imgs, **{**{global_key: self.global_params}, **self.values})
                global_key_found = True
                break
        if not global_key_found:
            out = self.apply(*imgs, **self.values)
        return out


class FilterCore(PureFilter):
    """PureFilter with cache storage + routing nodes defined (inputs & outputs fields)"""

    def __init__(self,
                 apply_fn: Callable = None,
                 name: Optional[str] = None,
                 default_params: dict = {},
                 inputs: List[Union[int, str]] = [0],
                 outputs: List[Union[int, str]] = [0],
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

    def run(self, *imgs) -> Tuple[Any]:
        if imgs:
            assert len(imgs) == len(
                self.inputs), "number of inputs shall match what's expected"
        if self.inputs is None:
            if imgs is not None:
                assert len(imgs) == 0
            filter_in = ()
        else:
            filter_in = imgs
        out = super().run(*filter_in)
        if out is None:
            return None
        if isinstance(out, tuple) or isinstance(out, list):
            assert len(out) >= len(
                self.outputs), "number of outputs shall be at least greater or equal to what's expected by the filter"
            return out

        else:
            logging.debug(
                f"need to return a tuple when you have a single element out {type(out)}")
            assert len(self.outputs) == 1, "returning a single element!"
            return (out,)

    def __repr__(self) -> str:
        descr = f"{self.name}: "
        descr += "(" + (", ".join([f"{it}" for it in self.inputs])) + ")"
        descr += " -> " + \
            "(" + ", ".join([f"{it}" for it in self.outputs]) + ")"
        # descr += "\n"
        return descr

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        control_dict = {}
        if hasattr(self, "controls"):
            for ctrl_name, ctrl in self.controls.items():
                control_dict[ctrl_name] = ctrl.value
        merged_kwargs = {**kwargs, **control_dict}
        out = self.apply(*args, **merged_kwargs)
        return out
