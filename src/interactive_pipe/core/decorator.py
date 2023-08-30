from interactive_pipe.core.control import Control
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.graphical.gui import InteractivePipeGUI
import functools
import inspect
from typing import Callable,Union

def interactive(**controls):
    """Function decorator to add some controls
    """
    def wrapper(func):
        for param_name, control in controls.items():
            Control.register(func.__name__, param_name, control)
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


def interactive_pipeline(gui=None, **kwargs_pipe) -> Union[HeadlessPipeline, InteractivePipeGUI]:
    """Function decorator to add some controls
    """
    def wrapper(pipeline_function):
        headless_pipeline = HeadlessPipeline.from_function(pipeline_function, **kwargs_pipe)
        if gui is None:
            return headless_pipeline
        if gui == "qt":
            from interactive_pipe.graphical.qt_gui import InteractivePipeQT as InteractivePipeGui   
        elif gui == "mpl":
            from interactive_pipe.graphical.mpl_gui import InteractivePipeMatplotlib as InteractivePipeGui
        else:
            raise NotImplementedError(f"Gui {gui} not available")
        gui_pipeline = InteractivePipeGui(pipeline=headless_pipeline)

        @functools.wraps(pipeline_function)
        def inner(*args, **kwargs):
            return gui_pipeline.__call__(*args)
        return inner
    return wrapper