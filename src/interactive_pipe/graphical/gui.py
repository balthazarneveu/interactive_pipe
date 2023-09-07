from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.data_objects.image import Image
from interactive_pipe.data_objects.parameters import Parameters
from interactive_pipe.graphical.keyboard import KeyboardControl
import logging
import numpy as np
from copy import deepcopy
from typing import Any, Callable, List
from functools import partial


class InteractivePipeGUI():
    """Interactive pipe with a graphical user interface"""
    def __init__(self, pipeline: HeadlessPipeline = None, controls=[], name="", custom_end=lambda :None, audio=False, size=None, **kwargs) -> None:
        self.pipeline = pipeline
        self.custom_end = custom_end
        self.audio = audio
        self.name = name
        self.size = size
        if hasattr(pipeline, "controls"):
            controls += pipeline.controls
        self.controls = controls
        self.pipeline.global_params["__app"] = self
        self.pipeline.global_params["__pipeline"] = self.pipeline
        if not "__events" in self.pipeline.global_params.keys():
            self.pipeline.global_params["__events"]={}
        self.key_bindings = {}
        self.context_key_bindings = {}
        self.init_app(**kwargs)
        self.reset_context_events()
        
    
    def init_app(self):
        raise NotImplementedError
    
    def run(self):
        raise NotImplementedError

    def __call__(self, *args, parameters={}, **kwargs) -> None:
        self.pipeline.parameters = parameters
        self.pipeline.parameters = self.pipeline.parameters_from_keyword_args(**kwargs)
        self.pipeline.inputs = args
        results = self.run()
        return results

    def bind_key(self, key, func: Callable):
        self.key_bindings[key] = func


    def bind_key_to_context(self, key:str, context_param_name: str, doc: str):
        self.context_key_bindings[key] = {
            'param_name': context_param_name,
            'doc': doc
        }
        self.pipeline.global_params["__events"][context_param_name] = False #Not triggered!

    def reset_context_events(self):
        for evkey in self.pipeline.global_params["__events"].keys():
            self.pipeline.global_params["__events"][evkey] = False

    def on_press(self, key_pressed, refresh_func=None):
        for key, func in self.key_bindings.items():
            if key_pressed == key:
                func() # a GUI level function like reset parameters or export images
        is_any_event_triggered = False
        for key, event_dict in self.context_key_bindings.items():
            
            event_triggered = key_pressed == key
            self.pipeline.global_params["__events"][event_dict["param_name"]] = event_triggered
            if event_triggered:
                logging.info(f"TRIGGERED A KEY EVENT {key_pressed} - {event_dict['doc']}")
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
        for keyboard_key, down_flag in [(ctrl.keyup, False), (ctrl.keydown, True)]:
            if keyboard_key is not None:
                if not down_flag:
                    toggle_only = False
                update_func = partial(key_update_parameter_func, slider_name, down_flag)
                if toggle_only:
                    doc = f"toggle {ctrl.name}"
                elif down_flag:
                    doc += f"[{ctrl.keydown}]/[{ctrl.keyup}]: {ctrl.name}"
                if len(doc) == 0:
                    update_func.__doc__ = None
                else:
                    update_func.__doc__ = doc
                self.bind_key(keyboard_key, update_func)

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
        self.pipeline.save(pth, data_wrapper_fn=lambda im:Image(im), save_entire_buffer=True)
    def display_graph(self):
        """display execution graph"""
        self.pipeline.graph_representation(view=True)
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
            help.append(f"[{key_context}]    : {event_dict['doc']} (context['__event'][{event_dict['param_name']}])")
        self.print_message(help)
        return help
    
    def print_message(self, message_list: List[str]):
        print("\n".join(message_list))

    # ---------------------------------------------------------------------


class InteractivePipeWindow():
    def __init__(self, *args, size=None, style=None, **kwargs) -> None:
        self.image_canvas = None
        self._size = size
        if style is not None:
            logging.info("no support for style in Qt backend")

    @property
    def size(self):
        return self._size

    @size.setter
    def size(self, _size):
        self._size = _size

    def add_image_placeholder(self, row, col):
        raise NotImplementedError

    def delete_image_placeholder(self, img_widget):
        raise NotImplementedError
    
    def update_image(self, content, row, col):
        raise NotImplementedError

    def check_image_canvas_changes(self, expected_image_canvas_shape):
        if self.image_canvas is not None:
            current_canvas_shape = (len(self.image_canvas), max([len(image_row) for image_row in self.image_canvas]))
            if current_canvas_shape != expected_image_canvas_shape:
                for row_content in self.image_canvas:
                    for img_widget in row_content:
                        if img_widget is not None:
                            self.delete_image_placeholder(img_widget)
                self.image_canvas = None
                logging.debug("Need to fully re-initialize canvas")
    
    def set_image_canvas(self, image_grid):
        expected_image_canvas_shape  = (len(image_grid), max([len(image_row) for image_row in image_grid]))
        # Check if the layout has been updated!
        self.check_image_canvas_changes(expected_image_canvas_shape)
        if self.image_canvas is None:
            self.image_canvas = np.empty(expected_image_canvas_shape).tolist()
            for row, image_row in enumerate(image_grid):
                for col, image_array in enumerate(image_row):
                    if image_array is None:
                        self.image_canvas[row][col] = None
                        continue
                    else:
                        self.add_image_placeholder(row, col)

    def set_images(self, image_grid):
        self.set_image_canvas(image_grid)
        for row, image_row in enumerate(image_grid):
            for col, image_array in enumerate(image_row):
                if image_array is None:
                    continue
                self.update_image(image_array, row, col)

    def refresh_display(self, _out):
        out = deepcopy(_out)
        # In case no canvas has been provided
        if isinstance(out, tuple):
            out = [list(out)]
        ny, nx = len(out), 0
        for idy, img_row in enumerate(out):
            if isinstance(img_row, list):
                for idx, out_img in enumerate(img_row):
                    if out[idy][idx] is not None:
                        out[idy][idx] = self.convert_image(out[idy][idx])
                nx = len(img_row)
            else:
                out[idy] = [self.convert_image(out[idy])]
        logging.info(f"{ny} x {nx} figures")
        self.set_images(out)