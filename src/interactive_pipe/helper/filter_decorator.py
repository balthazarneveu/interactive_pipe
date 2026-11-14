import difflib
import functools
import inspect
import logging
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from interactive_pipe.core.filter import FilterCore
from interactive_pipe.headless.control import Control, MappedChoiceControl
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.helper.annotation_controls import signature_with_defaults
from interactive_pipe.helper.choose_backend import get_interactive_pipeline_class
from interactive_pipe.helper.filter_entry_points import attach_filter_entry_points
from interactive_pipe.helper.keyword_args_analyzer import analyze_filter_controls


class EnhancedFilterCore(FilterCore):
    """Internally creates a pipeline with a single filter
    so you can graphically test a single filter without instantiating a pipeline.
    Internally used by `@interact` decorator.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.controls: Dict[str, Control] = {}

    def get_gui(self, gui="auto", output_routing=None, size=None):
        self.inputs = list(range(len(self.signature[0])))
        if output_routing is None:
            logging.warning(
                "Single output assumed, cannot deduce the number of outputs from your code,"
                "please provide output_routing!"
            )
            self.outputs = [
                "output",
            ]
        else:
            self.outputs = output_routing
        pipeline = HeadlessPipeline(filters=[self], inputs=[], outputs=None)
        for ctrl_name, _ctrl in self.controls.items():
            self.controls[ctrl_name].filter_to_connect = self
            self.controls[ctrl_name].parameter_name_to_connect = ctrl_name
        controls = [ctrl for _, ctrl in self.controls.items()]
        pipeline.controls = controls
        return get_interactive_pipeline_class(gui=gui)(pipeline=pipeline, size=size)

    def run_gui(self, *args, gui="auto", output_routing=None, size=None):
        try:
            self.inputs = list(range(len(args)))
            out = self.run(*args)
            if out is None:
                raise ValueError("Filter run returned None, cannot deduce output routing")
            output_routing = [f"output {idx}" for idx in range(len(out))]
            self.outputs = output_routing
        except Exception:
            # Broad on purpose: the dry run executes arbitrary user filter code.
            # Deduction is best-effort; fall back to the provided output_routing.
            logging.exception("cannot automatically deduce the output routing")
        gui_pipeline = self.get_gui(gui=gui, output_routing=output_routing, size=size)
        gui_pipeline.pipeline.inputs_routing = list(range(len(self.signature[0])))
        gui_pipeline(*args)
        gui_pipeline.close()
        gui_pipeline.controls = []
        del gui_pipeline


def interact(
    *decorator_args: Any,
    gui: str = "auto",
    disable: bool = False,
    output_routing: Optional[List[str]] = None,
    size: Union[str, Tuple[int, int], None] = None,
    inplace: bool = False,
    **decorator_controls: Any,
):
    """Launch a GUI from a single decorated function (one-shot decorator).

    Unlike ``@interactive``, decorating a function with ``@interact``
    immediately runs it inside a GUI: widgets are created for the declared
    controls and the window opens right away. Inspired by the ipywidgets
    ``interact`` function, except that returning numpy arrays or ``Curve``
    instances handles the display automatically — no matplotlib boilerplate.

    Args:
        *decorator_args: Positional inputs passed to the function
            (e.g. the input image).
        gui: Backend, same values as ``interactive_pipeline``
            (default ``"auto"``).
        disable: When True, return the function untouched (no GUI).
        output_routing: Names of the outputs, when they cannot be deduced
            from a dry run.
        size: Window/figure size hint forwarded to the backend.
        **decorator_controls: Controls bound to keyword arguments by name
            (``Control`` instances or the ``(default, [min, max])`` tuple
            shorthand).

    Example:
        ```python
        @interact(image, gain=(1.0, [0.0, 3.0]))
        def show(img, gain=1.0):
            return img * gain
        ```
    """
    omitted_parentheses_flag = False

    def wrapper(func):
        if disable:
            return func
        # this will run the GUI automatically
        filter_instance = filter_from_function(func, inplace=inplace, **decorator_controls)
        filter_instance.run_gui(
            *(decorator_args if not omitted_parentheses_flag else decorator_args[1:]),
            gui=gui,
            output_routing=output_routing,
            size=size,
        )
        # return the original function if you want to keep using it afterwards
        return func

    if len(decorator_args) == 1 and callable(decorator_args[0]):
        omitted_parentheses_flag = True
        return wrapper(decorator_args[0])  # no parenthesis
    return wrapper


def filter_from_function(apply_fn, default_params=None, inplace: bool = False, **kwargs) -> EnhancedFilterCore:
    if default_params is None:
        default_params = {}
    controls, filled_defaults = analyze_filter_controls(apply_fn, kwargs, localns=_caller_namespace(2))
    filter_instance = EnhancedFilterCore(
        apply_fn=_annotated_filter_wrapper(apply_fn, controls, filled_defaults, use_controls=False),
        default_params=default_params,
        inplace=inplace,
    )
    filter_instance.controls = controls
    return filter_instance


def _caller_namespace(depth: int) -> Optional[dict]:
    """Locals of the frame applying the decorator, to resolve string annotations
    (``from __future__ import annotations``) naming aliases local to a function."""
    try:
        frame = sys._getframe(depth + 1)
    except ValueError:
        return None
    try:
        return dict(frame.f_locals)
    finally:
        del frame


def _unknown_keyword_error(func: Callable, signature: inspect.Signature, kwargs: dict) -> Optional[TypeError]:
    accepts_any = any(p.kind == p.VAR_KEYWORD for p in signature.parameters.values())
    if accepts_any:
        return None
    names = [name for name, p in signature.parameters.items() if p.kind != p.POSITIONAL_ONLY]
    unknown = [key for key in kwargs if key not in names]
    if not unknown:
        return None
    hints = []
    for key in unknown:
        close = difflib.get_close_matches(key, names, n=1)
        if close:
            hints.append(f"{key!r} -> {close[0]!r}")
    suggestion = f" Did you mean {', '.join(hints)}?" if hints else ""
    return TypeError(
        f"{func.__name__}() got unexpected keyword argument(s) {', '.join(repr(k) for k in unknown)}. "
        f"Parameters: {', '.join(names)}.{suggestion}"
    )


def _annotated_filter_wrapper(
    func: Callable, controls: Dict[str, Control], filled_defaults: Dict[str, Any], use_controls: bool = True
) -> Callable:
    """Wrap a filter so that it can be called like the original function.

    - registered controls fill the keyword arguments not given explicitly
      (``use_controls``), so a direct call uses the live control values;
    - a value given positionally for a controlled parameter wins over the control;
    - dropdowns built from ``Enum`` / non-string ``Literal`` hints hand the filter
      the value (enum member, int...) instead of the displayed label;
    - parameters declared by an annotation without default get one in the
      wrapper's ``__signature__`` (they are controls, not inputs).
    """
    signature = inspect.signature(func)  # computed once, binding runs on every frame
    parameter_names = list(signature.parameters)
    choice_controls = {name: ctrl for name, ctrl in controls.items() if isinstance(ctrl, MappedChoiceControl)}
    if not use_controls and not choice_controls and not filled_defaults:
        return func

    @functools.wraps(func)
    def inner(*args, **kwargs):
        # Explicit kwargs take precedence: the pipeline engine passes each
        # filter instance's own values (a repeated filter gets per-instance
        # control clones). Registered controls fill the rest so a direct
        # call of the decorated function uses the live control values.
        positional = set(parameter_names[: len(args)])
        defaults = {name: value for name, value in filled_defaults.items() if name not in positional}
        if use_controls:
            control_kwargs = {name: ctrl for name, ctrl in controls.items() if name not in positional}
        else:
            control_kwargs = {}
        merged_kwargs = {**defaults, **control_kwargs, **kwargs}
        try:
            bound_args = signature.bind(*args, **merged_kwargs)
        except TypeError as exc:
            unknown = _unknown_keyword_error(func, signature, kwargs)
            if unknown is not None:
                raise unknown from None
            raise TypeError(f"{func.__name__}(): {exc}") from None
        bound_args.apply_defaults()

        for k, v in bound_args.arguments.items():
            if isinstance(v, Control):
                v = v.value
                bound_args.arguments[k] = v
            choice_control = choice_controls.get(k)
            if choice_control is not None:
                bound_args.arguments[k] = choice_control.to_value(v)

        # Call the original function with the processed arguments
        return func(*bound_args.args, **bound_args.kwargs)

    if filled_defaults:
        inner.__signature__ = signature_with_defaults(func, filled_defaults)  # type: ignore[attr-defined]
    return inner


def interactive(inplace: Union[bool, Callable] = False, **decorator_controls: Any):
    """Declare controls bound to a filter's keyword arguments.

    The decorated function keeps working as a plain function, but when used
    inside an ``@interactive_pipeline`` the declared controls appear as GUI
    widgets. Unlike ``@interact``, no GUI is launched at decoration time,
    so the filter can be reused across pipelines.

    Controls can also be declared by the filter's own annotations (see
    ``docs/guide/controls.md``): ``Annotated[float, (0.0, 3.0)]``,
    ``Annotated[bool, "label"]``, ``Annotated[T, Control(...)]``,
    ``Literal["a", "b"]`` and ``Enum`` hints make widgets, the default comes from
    the signature. A plain ``gain: float = 1.0`` makes no widget. A decorator
    argument wins over an annotation. ``@interactive`` also works without
    parentheses.

    Args:
        inplace: Declare that this filter mutates its input buffers. The
            engine then hands it private writable copies instead of
            read-only views. Prefer copying explicitly
            (``img = img.copy()``) in new code.
        **decorator_controls: Mapping of keyword-argument name to a control
            declaration — a ``Control`` instance (or subclass such as
            ``KeyboardControl``), the ``(default, [min, max])`` tuple
            shorthand, or a bare bool for a checkbox (``flip=True``). A bare
            number or string raises ``ValueError``: a slider needs a range,
            a dropdown a list of choices.

    Example:
        ```python
        @interactive(gain=(1.0, [0.0, 3.0]))
        def amplify(img, gain=1.0):
            return gain * img


        @interactive()
        def amplify_typed(img, gain: Annotated[float, (0.0, 3.0)] = 1.0):
            return gain * img
        ```
    """

    def wrapper(func, localns=None):
        if localns is None:
            localns = _caller_namespace(1)
        controls, filled_defaults = analyze_filter_controls(func, decorator_controls, localns=localns)
        inner = _annotated_filter_wrapper(func, controls, filled_defaults, use_controls=True)

        # picked up by HeadlessPipeline.from_function when building the FilterCore
        setattr(inner, "__interactive_pipe_inplace__", inplace)
        # inner.snapshot / .sweep / .describe / .summary / .interact (GitHub issue #21)
        attach_filter_entry_points(inner)
        return inner

    if callable(inplace) and not isinstance(inplace, bool):
        # bare @interactive (no parentheses): the decorated function comes in as `inplace`
        func, inplace = inplace, False
        return wrapper(func, localns=_caller_namespace(1))
    return wrapper
