import functools
import inspect
import logging
from typing import Dict

from interactive_pipe.core.filter import FilterCore
from interactive_pipe.headless.control import Control
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.helper.choose_backend import get_interactive_pipeline_class
from interactive_pipe.helper.keyword_args_analyzer import (
    get_controls_from_decorated_function_declaration,
)


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
            self.inputs = args
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
    *decorator_args,
    gui="auto",
    disable=False,
    output_routing=None,
    size=None,
    **decorator_controls,
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
        @interact(image, gain=(1.0, [0.0, 3.0]))
        def show(img, gain=1.0):
            return img * gain
    """
    omitted_parentheses_flag = False

    def wrapper(func):
        if disable:
            return func
        # this will run the GUI automatically
        filter_instance = filter_from_function(func, **decorator_controls)
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


def filter_from_function(apply_fn, default_params=None, **kwargs) -> EnhancedFilterCore:
    if default_params is None:
        default_params = {}
    controls = get_controls_from_decorated_function_declaration(apply_fn, kwargs)
    filter_instance = EnhancedFilterCore(apply_fn=apply_fn, default_params=default_params)
    filter_instance.controls = controls
    return filter_instance


def interactive(**decorator_controls):
    """Declare controls bound to a filter's keyword arguments.

    The decorated function keeps working as a plain function, but when used
    inside an ``@interactive_pipeline`` the declared controls appear as GUI
    widgets. Unlike ``@interact``, no GUI is launched at decoration time,
    so the filter can be reused across pipelines.

    Args:
        **decorator_controls: Mapping of keyword-argument name to a control
            declaration — a ``Control`` instance (or subclass such as
            ``KeyboardControl``) or the ``(default, [min, max])`` tuple
            shorthand.

    Example:
        @interactive(gain=(1.0, [0.0, 3.0]))
        def amplify(img, gain=1.0):
            return gain * img
    """

    def wrapper(func):
        controls = get_controls_from_decorated_function_declaration(func, decorator_controls)

        @functools.wraps(func)
        def inner(*args, **kwargs):
            # Explicit kwargs take precedence: the pipeline engine passes each
            # filter instance's own values (a repeated filter gets per-instance
            # control clones). Registered controls fill the rest so a direct
            # call of the decorated function uses the live control values.
            merged_kwargs = {**controls, **kwargs}
            bound_args = inspect.signature(func).bind(*args, **merged_kwargs)
            bound_args.apply_defaults()

            for k, v in bound_args.arguments.items():
                if isinstance(v, Control):
                    bound_args.arguments[k] = v.value

            # Call the original function with the processed arguments
            return func(*bound_args.args, **bound_args.kwargs)

        return inner

    return wrapper
