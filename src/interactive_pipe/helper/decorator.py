from interactive_pipe.headless.control import Control
from interactive_pipe.helper.control_abbreviation import control_from_tuple
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.core.graph import analyze_apply_fn_signature
import functools
import inspect
from typing import Callable,Union
import logging

__registered_controls_names = []
def interactive(**decorator_controls):
    """Function decorator to add some controls
    """
    def wrapper(func):
        controls = {}
        keyword_args = analyze_apply_fn_signature(func)[1]
        keyword_names =  list(keyword_args.keys())
        global __registered_controls_names
        
        # Analyze at 2 levels (function keyword args & decorator keyword args)  then register controls when necessary.
        #-------------------------------------------
        # @interactive(param_2=Control(...), )
        # def func(img1, img2, param_1=Control(...)):
        #-------------------------------------------
        
        # 1. Analyzing function keyword args 
        # def func(img1, img2, param_1=Control(...))
        
        for param_name, unknown_keyword_arg in keyword_args.items():
            chosen_control = None
            if isinstance(unknown_keyword_arg, Control): # This includes KeyboardControl aswell!!
                if unknown_keyword_arg.name is None or unknown_keyword_arg._auto_named:
                    unknown_keyword_arg.name = param_name
                chosen_control = unknown_keyword_arg
            else:
                if isinstance(unknown_keyword_arg, list) or isinstance(unknown_keyword_arg, tuple):
                    try:
                        chosen_control = control_from_tuple(unknown_keyword_arg, param_name=param_name)
                    except Exception as exc_1:
                        try:
                            chosen_control = control_from_tuple((unknown_keyword_arg,), param_name=param_name)
                        except Exception as exc:
                            raise Exception(exc)
                    # NOTE: for keyword args, setting a boolean will not trigger a tickmark (although it is possible)
                    # Use (True) instead of True if you want to make a tickbox
            if chosen_control is None:
                continue
            assert chosen_control.name not in __registered_controls_names, f"{chosen_control.name} already attributed - {__registered_controls_names}"
            __registered_controls_names.append(chosen_control.name)
            controls[param_name] = chosen_control
           
        
        # 2. Analyzing decorator keyword args 
        # @interactive(param_2=Control(...))
        for param_name, unknown_control in decorator_controls.items():
            chosen_control = None
            assert param_name in keyword_names, f"typo: control {param_name} passed through the decorator does not match any of the function keyword args {keyword_names}"
            if isinstance(unknown_control, Control):
                if unknown_control.name is None or unknown_control._auto_named:
                    unknown_control.name = param_name
                chosen_control = unknown_control
            else: # you may get a tuple, list or a boolean
                chosen_control = control_from_tuple(unknown_control, param_name=param_name)
            if chosen_control is None:
                continue
            assert chosen_control.name not in __registered_controls_names, f"{chosen_control.name} already attributed - {__registered_controls_names}"
            __registered_controls_names.append(chosen_control.name)
            controls[param_name] = chosen_control

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


def interactive_pipeline(gui=None, cache=False, output_canvas=None, **kwargs_gui) -> Union[HeadlessPipeline, InteractivePipeGUI]:
    """Function decorator to add some controls
    """
    def wrapper(pipeline_function):
        headless_pipeline = HeadlessPipeline.from_function(pipeline_function, cache=cache)
        if output_canvas is not None:
            headless_pipeline.outputs = output_canvas
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