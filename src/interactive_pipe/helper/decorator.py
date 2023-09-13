from interactive_pipe.headless.control import Control
from interactive_pipe.helper.keyword_args_analyzer import get_controls_from_decorated_function_declaration
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.graphical.gui import InteractivePipeGUI

import functools
import inspect
from typing import Callable,Union
from interactive_pipe.helper.choose_backend import get_interactive_pipeline_class


def interactive(**decorator_controls):
    """Function decorator to add some controls
    """
    def wrapper(func):
        controls = get_controls_from_decorated_function_declaration(func, decorator_controls)
        
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


def interactive_pipeline(gui=None, cache=False, output_canvas=None, **kwargs_gui) -> Union[HeadlessPipeline, InteractivePipeGUI]:
    """@interactive_pipeline

    Function decorator to add some controls @interactive_pipeline
    """
    def wrapper(pipeline_function):
        headless_pipeline = HeadlessPipeline.from_function(pipeline_function, cache=cache)
        if output_canvas is not None:
            headless_pipeline.outputs = output_canvas
        if gui is None:
            return headless_pipeline
        else:
            InteractivePipeGui = get_interactive_pipeline_class(gui)
            gui_pipeline = InteractivePipeGui(pipeline=headless_pipeline, name=pipeline_function.__name__, **kwargs_gui)

        @functools.wraps(pipeline_function)
        def inner(*args, **kwargs):
            return gui_pipeline.__call__(*args, **kwargs)
        return inner
    return wrapper