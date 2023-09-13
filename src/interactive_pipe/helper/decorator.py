from interactive_pipe.headless.control import Control
from interactive_pipe.helper.control_abbreviation import control_from_tuple
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.core.graph import analyze_apply_fn_signature
from interactive_pipe.core.filter import FilterCore
import functools
import inspect
from typing import Callable,Union
import logging

__registered_controls_names = []

def __create_control_from_keyword_argument(
        param_name: str,
        unknown_keyword_arg: Union[Control, list, tuple]
    ) -> Union[None, Control]:
    """Create a Control from a given keyword argument named  param_name with value unknown_keyword_arg
    
    - If unknown_keyword_arg is already a Control, nothing to do.
    - If unknown_keyword_arg is a tuple or a list or something else, 
    guess the Slider declaration automatically (see `control_from_tuple`)

    You cannot have several controls which have the same attribute .name
    See https://github.com/balthazarneveu/interactive_pipe/issues/35 for more details
    """
    chosen_control = None
    global __registered_controls_names
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
    if chosen_control is not None:
        assert chosen_control.name not in __registered_controls_names, f"{chosen_control.name} already attributed - {__registered_controls_names}"
        __registered_controls_names.append(chosen_control.name)
    return chosen_control

def __get_controls_from_decorated_function_declaration(func: Callable, decorator_controls: dict):
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
        chosen_control = __create_control_from_keyword_argument(param_name, unknown_keyword_arg)
        if chosen_control is not None:
            controls[param_name] = chosen_control
        
    
    # 2. Analyzing decorator keyword args 
    # @interactive(param_2=Control(...))
    for param_name, unknown_keyword_arg in decorator_controls.items():
        assert param_name in keyword_names, f"typo: control {param_name} passed through the decorator does not match any of the function keyword args {keyword_names}"
        chosen_control = __create_control_from_keyword_argument(param_name, unknown_keyword_arg)
        if chosen_control is not None:
            controls[param_name] = chosen_control

    for param_name, unknown_control in controls.items():
        Control.register(func.__name__, param_name, controls[param_name])
    return controls


def interactive(**decorator_controls):
    """Function decorator to add some controls
    """
    def wrapper(func):
        controls = __get_controls_from_decorated_function_declaration(func, decorator_controls)
        
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

class EnhancedFilterCore(FilterCore):
    def get_gui(self, gui="qt", output_routing=None):
        self.inputs = list(range(len(self.signature[0])))
        if output_routing is None:
            logging.warning("Single output assumed, cannot deduce the number of outputs from your code, please provide output_routing!")
            self.outputs = ["output",]
        else:
            self.outputs = output_routing
        pipeline = HeadlessPipeline(filters=[self])
        for ctrl_name, ctrl in self.controls.items():
            self.controls[ctrl_name].filter_to_connect = self
            self.controls[ctrl_name].parameter_name_to_connect = ctrl_name
        controls = [ctrl for _, ctrl in self.controls.items()]
        pipeline.controls = controls
        return get_interactive_pipeline_class(gui=gui)(pipeline=pipeline)

    def run_gui(self, *args, gui="qt", output_routing=None):
        try:
            self.inputs = args
            out = self.run(*args)   
            output_routing = [f"output {idx}" for idx in range(len(out))]
            self.outputs = output_routing
        except Exception as exc:
            logging.warning(f"cannot automatically deduce the output routing\n{exc}")
        gui_pipeline = self.get_gui(gui=gui, output_routing=output_routing)
        gui_pipeline.pipeline.inputs_routing = list(range(len(self.signature[0])))    
        gui_pipeline(*args)
        gui_pipeline.close()
        gui_pipeline.controls = []
        del gui_pipeline


def play(*args, gui="qt", output_routing = None, **decorator_controls):
    """play decorator allows to test a single filter"""
    def wrapper(func):
        global __registered_controls_names
        __registered_controls_names = []
        filter_instance = filter_from_function(func, **decorator_controls)
        filter_instance.run_gui(*args, gui=gui, output_routing=output_routing)
    return wrapper


def filter_from_function(apply_fn, default_params={}, **kwargs) -> EnhancedFilterCore:
    controls = __get_controls_from_decorated_function_declaration(apply_fn, kwargs)
    filter_instance = EnhancedFilterCore(apply_fn=apply_fn, default_params=default_params)
    filter_instance.controls = controls
    return filter_instance

def pipeline(pipeline_function:Callable, **kwargs) -> HeadlessPipeline:
    return HeadlessPipeline.from_function(pipeline_function, **kwargs)


def get_interactive_pipeline_class(gui="qt"):
    if gui == "qt":
        from interactive_pipe.graphical.qt_gui import InteractivePipeQT as ChosenGui
    elif gui == "mpl":
        from interactive_pipe.graphical.mpl_gui import InteractivePipeMatplotlib as ChosenGui
    elif gui == "nb":
        from interactive_pipe.graphical.nb_gui import InteractivePipeJupyter as ChosenGui
    else:
        raise NotImplementedError(f"Gui {gui} not available")
    return ChosenGui


def interactive_pipeline(gui=None, cache=False, output_canvas=None, **kwargs_gui) -> Union[HeadlessPipeline, InteractivePipeGUI]:
    """Function decorator to add some controls
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