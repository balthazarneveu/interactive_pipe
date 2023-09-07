from interactive_pipe.headless.control import Control
from interactive_pipe.headless.control_abbreviation import control_from_tuple
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.core.graph import analyze_apply_fn_signature
import functools
import inspect
from typing import Callable,Union

def interactive(**decorator_controls):
    """Function decorator to add some controls
    """
    def wrapper(func):
        controls = {}
        keyword_args = analyze_apply_fn_signature(func)[1]
        keyword_names =  list(keyword_args.keys())
        for param_name, unknown_keyword_arg in keyword_args.items():
            if isinstance(unknown_keyword_arg, Control):
                if unknown_keyword_arg.name is None or unknown_keyword_arg._auto_named:
                    unknown_keyword_arg.name = param_name
                controls[param_name] = unknown_keyword_arg
            else:
                if isinstance(unknown_keyword_arg, list) or isinstance(unknown_keyword_arg, tuple):
                    controls[param_name] = control_from_tuple(unknown_keyword_arg, param_name=param_name)
                    # NOTE: for keyword args, setting a boolean will not trigger a tickmark (although it is possible)
                    # Use (True) instead of True if you want to make a tickbox


        for param_name, unknown_control in decorator_controls.items():
            assert param_name in keyword_names, f"typo: control {param_name} passed through the decorator does not match any of the function keyword args {keyword_names}"
            if isinstance(unknown_control, Control):
                controls[param_name] = unknown_control
            else: # you may get a tuple, list or a boolean
                controls[param_name] = control_from_tuple(unknown_control, param_name=param_name)

        for param_name, unknown_control in controls.items():
            Control.register(func.__name__, param_name, controls[param_name])
        @functools.wraps(func)
        def inner(*args, **kwargs):
            # Combine args and kwargs into a single dictionary
            merged_kwargs = {**kwargs, **controls}
            bound_args = inspect.signature(func).bind(*args, **merged_kwargs)
            bound_args.apply_defaults()
            
            for k, v in bound_args.arguments.items():
                if isinstance(v, Control):
                    bound_args.arguments[k] = v.value
            
            # Call the original function with the processed arguments
            return func(*bound_args.args, **bound_args.kwargs)
        return inner
    return wrapper


def pipeline(pipeline_function:Callable, **kwargs) -> HeadlessPipeline:
    return HeadlessPipeline.from_function(pipeline_function, **kwargs)


def interactive_pipeline(gui=None, cache=False, **kwargs_gui) -> Union[HeadlessPipeline, InteractivePipeGUI]:
    """Function decorator to add some controls
    """
    def wrapper(pipeline_function):
        headless_pipeline = HeadlessPipeline.from_function(pipeline_function, cache=cache)
        if gui is None:
            return headless_pipeline
        if gui == "qt":
            from interactive_pipe.graphical.qt_gui import InteractivePipeQT as InteractivePipeGui   
        elif gui == "mpl":
            from interactive_pipe.graphical.mpl_gui import InteractivePipeMatplotlib as InteractivePipeGui
        elif gui == "nb":
            from interactive_pipe.graphical.nb_gui import InteractivePipeJupyter as InteractivePipeGui
        else:
            raise NotImplementedError(f"Gui {gui} not available")
        gui_pipeline = InteractivePipeGui(pipeline=headless_pipeline, name=pipeline_function.__name__, **kwargs_gui)

        @functools.wraps(pipeline_function)
        def inner(*args, **kwargs):
            return gui_pipeline.__call__(*args, **kwargs)
        return inner
    return wrapper