from interactive_pipe.headless.control import Control
import functools
import inspect
from interactive_pipe.helper.keyword_args_analyzer import get_controls_from_decorated_function_declaration
from interactive_pipe.helper import _private #import registered_controls_names
from interactive_pipe.headless.pipeline import HeadlessPipeline

from interactive_pipe.core.filter import FilterCore
import logging

from interactive_pipe.helper.choose_backend import get_interactive_pipeline_class

class EnhancedFilterCore(FilterCore):
    def get_gui(self, gui="qt", output_routing=None):
        self.inputs = list(range(len(self.signature[0])))
        if output_routing is None:
            logging.warning("Single output assumed, cannot deduce the number of outputs from your code, please provide output_routing!")
            self.outputs = ["output",]
        else:
            self.outputs = output_routing
        pipeline = HeadlessPipeline(filters=[self])
        for ctrl_name, _ctrl in self.controls.items():
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


def interact(*args, gui="qt", output_routing = None, **decorator_controls):
    """interact decorator allows to launch a GUI from a single function
    
    This will directly launch a GUI.
    """
    def wrapper(func):
        _private.registered_controls_names = []
        filter_instance = filter_from_function(func, **decorator_controls)
        filter_instance.run_gui(*args, gui=gui, output_routing=output_routing)
    return wrapper


def filter_from_function(apply_fn, default_params={}, **kwargs) -> EnhancedFilterCore:
    controls = get_controls_from_decorated_function_declaration(apply_fn, kwargs)
    filter_instance = EnhancedFilterCore(apply_fn=apply_fn, default_params=default_params)
    filter_instance.controls = controls
    return filter_instance


def interactive(**decorator_controls):
    """
    `@interactive` differrs from `interact` in the sense that it will not launch a gui.
    It is simply used to declare some sliders and allows re-using these functions afterwards.
    Function decorator to add some controls
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