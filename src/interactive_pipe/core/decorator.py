from interactive_pipe.core.control import Control
from interactive_pipe.headless.pipeline import HeadlessPipeline
import functools
import inspect
from typing import Callable

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


def interactive_pipeline(pipeline_function:Callable, **kwargs) -> HeadlessPipeline:
    return HeadlessPipeline.from_function(pipeline_function, **kwargs)