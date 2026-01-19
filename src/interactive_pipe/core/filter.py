import logging
from copy import deepcopy
from typing import Callable, List, Optional, Union, Tuple, Any

from interactive_pipe.core.cache import CachedResults
from interactive_pipe.core.signature import analyze_apply_fn_signature
from interactive_pipe.core.context import _set_framework_state, SharedContext

EQUIVALENT_STATE_KEYS = [
    "global_params",
    "global_parameters",
    "global_state",
    "global_context",
    "context",
    "state",
]

# Sentinel object to distinguish between "not provided" and "explicitly None"
_SENTINEL = object()


class PureFilter:
    def __init__(
        self,
        apply_fn: Optional[Callable] = None,
        name: Optional[str] = None,
        default_params: Optional[dict] = None,
    ):
        if default_params is None:
            default_params = {}
        self.name = (
            name
            if name
            else (self.__class__.__name__ if not apply_fn else apply_fn.__name__)
        )
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
        if not isinstance(new_global_params, dict):
            raise TypeError(
                f"global_params must be a dict, got {type(new_global_params)}"
            )
        self._global_params = new_global_params

    def check_apply_signature(self):
        if not hasattr(self, "__args_names") or not hasattr(self, "__kwargs_names"):
            self.__args_names, self.__kwargs_names = analyze_apply_fn_signature(
                self.apply
            )
            self.signature = (self.__args_names, self.__kwargs_names)

    def __initialize_default_values(self):
        if hasattr(self, "_values"):
            raise RuntimeError("_values attribute already exists")
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
        if not isinstance(new_values, dict):
            raise TypeError(f"{new_values} is not a dictionary")
        self._values = {**self._values, **new_values}

    def run(self, *imgs) -> Any:
        # First we check if the keyword args of the apply function match with self.values
        if not isinstance(self.values, dict):
            raise TypeError(f"self.values must be a dict, got {type(self.values)}")
        self.check_apply_signature()
        for key, val in self.values.items():
            if key not in self.__kwargs_names.keys():
                raise ValueError(
                    f"{self.name}: {key} not in {self.__kwargs_names.keys()}"
                )

        # Set framework state for context-based API (layout, audio, etc.)
        _set_framework_state(self.global_params)
        try:
            global_key_found = False
            for global_key in EQUIVALENT_STATE_KEYS:
                if global_key in self.__kwargs_names.keys():
                    # Warn about deprecated parameter injection (any magic parameter name)
                    SharedContext._warn_deprecation_once()

                    # Inject the context dictionary (legacy API)
                    out = self.apply(
                        *imgs, **{**{global_key: self.global_params}, **self.values}
                    )
                    global_key_found = True
                    break
            if not global_key_found:
                out = self.apply(*imgs, **self.values)
            return out
        finally:
            # Clear framework state after execution
            _set_framework_state(None)


class FilterCore(PureFilter):
    """PureFilter with cache storage + routing nodes defined (inputs & outputs fields)"""

    def __init__(
        self,
        apply_fn: Callable = None,
        name: Optional[str] = None,
        default_params: Optional[dict] = None,
        inputs: Optional[List[Union[int, str]]] = _SENTINEL,
        outputs: Optional[List[Union[int, str]]] = _SENTINEL,
        cache=True,
    ):
        if default_params is None:
            default_params = {}
        if inputs is _SENTINEL:
            inputs = [0]
        elif inputs is None:
            # Explicitly None means no inputs
            inputs = None
        if outputs is _SENTINEL:
            outputs = [0]
        elif outputs is None:
            # Explicitly None means no outputs (though this is less common)
            outputs = None
        super().__init__(apply_fn=apply_fn, name=name, default_params=default_params)
        self.inputs = inputs
        self.outputs = outputs
        self.cache = cache
        self.reset_cache()

    def reset_cache(self):
        if self.cache:
            self.cache_mem = CachedResults(self.name)
        else:
            self.cache_mem = None

    def run(self, *imgs) -> Optional[Tuple[Any]]:
        if imgs:
            if len(imgs) != len(self.inputs):
                raise ValueError(
                    f"number of inputs ({len(imgs)}) shall match what's expected ({len(self.inputs)})"
                )
        if self.inputs is None:
            if len(imgs) > 0:
                raise ValueError(
                    f"Expected no inputs when self.inputs is None, got {len(imgs)}"
                )
            filter_in = ()
        else:
            filter_in = imgs
        out = super().run(*filter_in)
        if out is None:
            return None
        if isinstance(out, tuple) or isinstance(out, list):
            if len(out) < len(self.outputs):
                raise ValueError(
                    f"number of outputs ({len(out)}) shall be at least greater or equal "
                    f"to what's expected by the filter ({len(self.outputs)})"
                )
            return out

        else:
            logging.debug(
                f"need to return a tuple when you have a single element out {type(out)}"
            )
            if len(self.outputs) != 1:
                raise ValueError(
                    f"returning a single element but expected {len(self.outputs)} outputs!"
                )
            return (out,)

    def __repr__(self) -> str:
        descr = f"{self.name}: "
        if self.inputs is None:
            descr += "()"
        else:
            descr += "(" + (", ".join([f"{it}" for it in self.inputs])) + ")"
        descr += " -> "
        if self.outputs is None:
            descr += "()"
        else:
            descr += "(" + ", ".join([f"{it}" for it in self.outputs]) + ")"
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
