import ast
import inspect
import logging
import textwrap
from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from interactive_pipe.core.cache import CachedResults
from interactive_pipe.core.context import REMOVED_CONTEXT_KWARGS, _set_current_filter, _set_framework_state
from interactive_pipe.core.framework_state import FrameworkState
from interactive_pipe.core.signature import analyze_apply_fn_signature

# Sentinel object to distinguish between "not provided" and "explicitly None"
_SENTINEL = object()


class FilterOutputError(ValueError):
    """A filter returned something that does not fit the pipeline line calling it
    (wrong number of values, or ``None`` from a filter without ``return``).

    Raised by the framework, not by user code: ``FilterError`` shows the
    pipeline line instead of a framework traceback.
    """

    framework_check = True


_RETURNS_VALUE_CACHE: Dict[Any, bool] = {}


def _returns_a_value(func: Callable) -> bool:
    """True unless the function source provably has no ``return <value>`` (nor ``yield``).

    Unknown (no source, builtins, lambdas...) counts as True: only a sure
    "forgot the return" is reported.
    """
    func = inspect.unwrap(func)
    code = getattr(func, "__code__", None)
    if code is None:
        return True
    if code in _RETURNS_VALUE_CACHE:
        return _RETURNS_VALUE_CACHE[code]
    result = True
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
        function_node = next(
            node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        nested = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)

        def walk(node):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, nested):
                    continue
                yield child
                yield from walk(child)

        result = any(
            (isinstance(node, ast.Return) and node.value is not None) or isinstance(node, (ast.Yield, ast.YieldFrom))
            for node in walk(function_node)
        )
    except (OSError, TypeError, SyntaxError, StopIteration, IndentationError):
        result = True
    _RETURNS_VALUE_CACHE[code] = result
    return result


class PureFilter:
    def __init__(
        self,
        apply_fn: Optional[Callable] = None,
        name: Optional[str] = None,
        default_params: Optional[dict] = None,
    ):
        if default_params is None:
            default_params = {}
        self.name = name if name else (self.__class__.__name__ if not apply_fn else apply_fn.__name__)
        if apply_fn is not None:
            self.apply = apply_fn
        self._global_params = {}
        # Standalone filters own a default state; a pipeline replaces it with
        # its shared one when the filter is attached.
        self.framework_state = FrameworkState()
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
            raise TypeError(f"global_params must be a dict, got {type(new_global_params)}")
        self._global_params = new_global_params

    def check_apply_signature(self):
        if not hasattr(self, "_args_names") or not hasattr(self, "_kwargs_names"):
            self._args_names, self._kwargs_names = analyze_apply_fn_signature(self.apply)
            self.signature = (self._args_names, self._kwargs_names)

    def __initialize_default_values(self):
        if hasattr(self, "_values"):
            raise RuntimeError("_values attribute already exists")
        self.check_apply_signature()
        for magic_key in REMOVED_CONTEXT_KWARGS:
            if magic_key in self._kwargs_names.keys():
                raise TypeError(
                    f"Filter '{self.name}' declares keyword argument '{magic_key}': implicit context "
                    "injection (global_params) was removed in interactive_pipe 0.9.0. Remove this "
                    "parameter and use the proxies instead - from interactive_pipe import context, "
                    "layout, audio - e.g. context['key'] for shared state, layout.style()/layout.grid() "
                    "for display. If you meant an ordinary parameter, rename it."
                )
        self._values = dict(self._kwargs_names)

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
            if key not in self._kwargs_names.keys():
                raise ValueError(f"{self.name}: {key} not in {self._kwargs_names.keys()}")

        # Set framework state for context-based API (layout, audio, events, etc.)
        _set_framework_state(self.framework_state)
        _set_current_filter(self.name)
        try:
            return self.apply(*imgs, **self.values)
        finally:
            # Clear framework state after execution
            _set_current_filter(None)
            _set_framework_state(None)


class FilterCore(PureFilter):
    """PureFilter with cache storage + routing nodes defined (inputs & outputs fields)"""

    def __init__(
        self,
        apply_fn: Optional[Callable] = None,
        name: Optional[str] = None,
        default_params: Optional[dict] = None,
        inputs: Optional[List[Union[int, str]]] = _SENTINEL,  # type: ignore
        outputs: Optional[List[Union[int, str]]] = _SENTINEL,  # type: ignore
        cache=True,
        inplace: bool = False,
    ):
        """inplace: declare that this filter mutates its inputs. The engine then hands it
        private writable deep copies instead of read-only views, keeping shared buffers
        and upstream caches safe. Prefer copying explicitly (img = img.copy()) in new code."""
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
        self.inplace = inplace
        # where a pipeline body calls this filter (set by HeadlessPipeline.from_function):
        # enables the output-count checks and names the line in their messages
        self.call_location: Optional[dict] = None
        self.reset_cache()

    def reset_cache(self):
        if self.cache:
            self.cache_mem = CachedResults(self.name)
        else:
            self.cache_mem = None

    def run(self, *imgs) -> Optional[Tuple[Any, ...]]:
        if imgs:
            if self.inputs is not None and len(imgs) != len(self.inputs):
                raise ValueError(f"number of inputs ({len(imgs)}) shall match what's expected ({len(self.inputs)})")
        if self.inputs is None:
            if len(imgs) > 0:
                raise ValueError(f"Expected no inputs when self.inputs is None, got {len(imgs)}")
            filter_in = ()
        else:
            filter_in = imgs
        out = super().run(*filter_in)
        # Filters built from a pipeline body know the line calling them: the
        # returned values must match the names it assigns. Filters assembled by
        # hand keep the historical lenient behaviour (extra values dropped).
        strict = getattr(self, "call_location", None) is not None
        expected = len(self.outputs) if self.outputs else 0
        if out is None:
            if strict and expected and not _returns_a_value(self.apply):
                raise self._output_error(
                    "returned None: the function has no `return` statement",
                    f"add `return <result>` at the end of '{self._function_name() or self.name}'",
                )
            return None
        if self.outputs is not None and len(self.outputs) == 0:
            # a bare call `f(img)`: nothing assigns the result, it is dropped (like Python)
            return None
        if strict and expected == 1 and isinstance(out, list):
            # `x = f(img)` with f returning a list: lists are data, x is the list
            # whatever its length (only a tuple is unpacked into one name)
            return (out,)
        if isinstance(out, (tuple, list)):
            if self.outputs is not None and len(out) < len(self.outputs):
                raise self._output_error(
                    f"returned {len(out)} value(s) but the pipeline unpacks {len(self.outputs)}",
                    self._count_fix(len(out)),
                )
            if strict and expected and len(out) > expected:
                raise self._output_error(
                    f"returned {len(out)} values but the pipeline assigns {expected} name(s)",
                    self._count_fix(len(out)),
                )
            return out  # type: ignore

        else:
            logging.debug(f"need to return a tuple when you have a single element out {type(out)}")
            if self.outputs is not None and len(self.outputs) != 1:
                raise self._output_error(
                    f"returned a single {type(out).__name__} but the pipeline unpacks {len(self.outputs)} values",
                    self._count_fix(1),
                )
            return (out,)

    def _count_fix(self, returned: int) -> str:
        names = ", ".join(f"out{idx}" for idx in range(returned)) if returned > 0 else "..."
        inputs = ", ".join(str(name) for name in (self.inputs or []))
        return (
            f"unpack exactly what the filter returns (`{names} = {self.name}({inputs})`) or change its `return`; "
            "to keep a tuple as one value, return it wrapped (`return (values,)`) or as a list "
            "(a list assigned to one name is kept whole)"
        )

    def _function_name(self) -> Optional[str]:
        """Name of the Python function behind the filter (None for a callable object)."""
        import inspect

        try:
            function = inspect.unwrap(self.apply)
        except ValueError:  # pragma: no cover - wrapper loop
            function = self.apply
        return getattr(function, "__name__", None)

    def _label(self) -> str:
        """``filter 'split'``, plus the function name when the pipeline calls it by another name
        (``split = two_values`` / repeated filter copies): ``filter 'split' (function 'two_values')``."""
        function_name = self._function_name()
        if function_name and function_name != self.name and function_name != "<lambda>":
            return f"filter '{self.name}' (function '{function_name}')"
        return f"filter '{self.name}'"

    def _output_error(self, problem: str, fix: str) -> "FilterOutputError":
        message = f"{self._label()} {problem}"
        location = getattr(self, "call_location", None)
        if location:
            where = (
                f"pipeline '{location.get('pipeline_name')}', {location.get('filename')}, line {location.get('lineno')}"
            )
            message += f"\n    at {where}"
            if location.get("source_line"):
                message += f": {location['source_line'].strip()}"
        message += f"\n    Fix: {fix}"
        return FilterOutputError(message)

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
        controls = getattr(self, "controls", None)
        if controls is not None:
            for ctrl_name, ctrl in controls.items():
                control_dict[ctrl_name] = ctrl.value
        merged_kwargs = {**kwargs, **control_dict}
        out = self.apply(*args, **merged_kwargs)
        return out
