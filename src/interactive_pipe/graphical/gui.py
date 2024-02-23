from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.data_objects.image import Image
from interactive_pipe.data_objects.parameters import Parameters
from interactive_pipe.headless.keyboard import KeyboardControl
import logging
from typing import Callable, List
from functools import partial


class InteractivePipeGUI():
    """Adds a generic graphical user interface to HeadlessPipeline.

    Needs to be specified/customized for each backend.
    It adds an app with a GUI on top of a HeadlessPipeline.
    Widgets will update the pipeline parameters.
    - It deals with key bindings
     (keyboard press triggers a function. 
     function docstring is shown to the user when he presses "F1" help)
    - It deals with printing the help
    - Initializing the app `init_app` usually requires creating the window object
    A few special methods may be redefined for some specific backend needs.
    `reset_parameters`, `close`,
    `save_parameters`, `load_parameters`, `print_parameters`
    `display_graph`, `help`
    Docstring of these methods will be used in the "F1" help descriptions
    - Redefining `print_message` will allow a window popup for instance.

    Do not re-implement the init function!
    """

    def __init__(self, pipeline: HeadlessPipeline = None, controls=[], name="", custom_end=lambda: None, audio=False, size=None, **kwargs) -> None:
        self.pipeline = pipeline
        self.custom_end = custom_end
        self.audio = audio
        self.name = name
        self.size = size
        merged_controls = []
        merged_controls += controls
        if hasattr(pipeline, "controls"):
            merged_controls += pipeline.controls
        self.controls = merged_controls
        if self.pipeline.outputs:
            if not isinstance(self.pipeline.outputs[0], list):
                self.pipeline.outputs = [self.pipeline.outputs]
        self.pipeline.global_params["__output_styles"] = {}
        self.pipeline.global_params["__app"] = self
        self.pipeline.global_params["__pipeline"] = self.pipeline
        if not "__events" in self.pipeline.global_params.keys():
            self.pipeline.global_params["__events"] = {}
        self.key_bindings = {}
        self.context_key_bindings = {}
        self.init_app(**kwargs)
        self.reset_context_events()

    def init_app(self):
        """Init the app
        Initializing the app requires
        - creating the window object
        - binding default keyboard keys
        """
        raise NotImplementedError

    def run(self) -> list:
        """Once properly initialized
        - Show the window
        - Put it in full screen if needed
        - execute the app (launch the main event loop)
        Return results
        """
        raise NotImplementedError

    def __call__(self, *args, parameters={}, **kwargs) -> None:
        self.pipeline.parameters = parameters
        self.pipeline.parameters = self.pipeline.parameters_from_keyword_args(
            **kwargs)
        self.pipeline.inputs = args
        results = self.run()
        return results

    def bind_key(self, key, func: Callable):
        self.key_bindings[key] = func

    def bind_key_to_context(self, key: str, context_param_name: str, doc: str):
        self.context_key_bindings[key] = {
            'param_name': context_param_name,
            'doc': doc
        }
        # Not triggered!
        self.pipeline.global_params["__events"][context_param_name] = False

    def reset_context_events(self):
        for evkey in self.pipeline.global_params["__events"].keys():
            self.pipeline.global_params["__events"][evkey] = False

    def on_press(self, key_pressed, refresh_func=None):
        for key, func in self.key_bindings.items():
            if key_pressed == key:
                func()  # a GUI level function like reset parameters or export images
        is_any_event_triggered = False
        for key, event_dict in self.context_key_bindings.items():

            event_triggered = key_pressed == key
            self.pipeline.global_params["__events"][event_dict["param_name"]
                                                    ] = event_triggered
            if event_triggered:
                logging.info(
                    f"TRIGGERED A KEY EVENT {key_pressed} - {event_dict['doc']}")
                is_any_event_triggered = True
        if is_any_event_triggered:
            self.pipeline.reset_cache()
            refresh_func()
        self.reset_context_events()

    def bind_keyboard_slider(self, ctrl: KeyboardControl, key_update_parameter_func: Callable):
        assert isinstance(ctrl, KeyboardControl)
        toggle_only = True
        doc = ""
        slider_name = ctrl.name
        toggle_only = ctrl.keyup is None or ctrl.keydown is None

        for keyboard_key, down_flag in [(ctrl.keyup, False), (ctrl.keydown, True)]:
            if keyboard_key is None:
                continue
            if toggle_only:
                if ctrl._type == bool:
                    doc = f"toggle {ctrl.name}"
                else:
                    if ctrl.keyup is None:
                        doc = f"decrease {ctrl.name}"
                    elif ctrl.keydown is None:
                        doc = f"increase {ctrl.name}"
            else:
                if down_flag:
                    doc = f"[{ctrl.keydown}]/[{ctrl.keyup}]: {ctrl.name}"
                else:
                    doc = None
            update_func = partial(
                key_update_parameter_func, slider_name, down_flag)
            self.bind_key(keyboard_key, update_func)
            update_func.__doc__ = doc

    # ---------------------------------------------------------------------
    def reset_parameters(self):
        """reset parameters"""
        logging.debug("Reset parameters")

    def close(self):
        """quit"""
        logging.debug("Closing gui")

    def save_parameters(self):
        """export parameters dictionary to a yaml/json file"""
        self.pipeline.export_tuning()

    def load_parameters(self):
        """import parameters dictionary from a yaml/json file on disk"""
        pth = Parameters.check_path(Parameters.prompt_file())
        self.pipeline.import_tuning(pth)

    def print_parameters(self):
        """print parameters dictionary in the console"""
        print(self.pipeline.__repr__())

    def save_images(self):
        """save images to disk"""
        pth = Image.check_path(Image.prompt_file(), load=False)
        self.pipeline.save(pth, data_wrapper_fn=lambda im: Image(
            im), save_entire_buffer=True)

    def display_graph(self):
        """display execution graph"""
        self.pipeline.graph_representation(view=True, ortho=False)

    def help(self) -> List[str]:
        """print this help in the console"""
        help = []
        for key, func in self.key_bindings.items():
            if func.__doc__ is not None:
                if func.__doc__.startswith("["):
                    help.append(f"{func.__doc__}")
                else:
                    help.append(f"[{key}]    : {func.__doc__}")
        for key_context, event_dict in self.context_key_bindings.items():
            help.append(
                f"[{key_context}]    : {event_dict['doc']} (context['__event'][{event_dict['param_name']}])")
        self.print_message(help)
        return help

    def print_message(self, message_list: List[str]):
        print("\n".join(message_list))

    # ---------------------------------------------------------------------
