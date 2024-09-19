import gradio as gr
import time
from pathlib import Path
import sys
import numpy as np
from typing import List
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.graphical.gradio_control import ControlFactory
from interactive_pipe.graphical.window import InteractivePipeWindow
from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.headless.control import Control
import logging
from copy import deepcopy
PYQTVERSION = None
MPL_SUPPORT = False


def refresh_app(slider_value):
    # Create an array with values scaled by the slider value
    image = np.ones((256, 256, 3)) * (slider_value / 100) * 255
    image = image.astype(np.uint8)  # Ensure the output is in the correct format (uint8)
    # print(image)
    blk = np.zeros((256, 256, 3))
    return image, blk


class InteractivePipeGradio(InteractivePipeGUI):
    def init_app(self, **kwargs):
        self.window = MainWindow(controls=self.controls, name=self.name,
                                 pipeline=self.pipeline, size=self.size, main_gui=self, **kwargs)
        self.pipeline.global_params["__pipeline"] = self.pipeline
        self.set_default_key_bindings()

    def run(self) -> list:
        assert self.pipeline._PipelineCore__initialized_inputs, "Did you forget to initialize the pipeline inputs?"
        self.window.refresh()
        self.custom_end()
        return self.pipeline.results

    def set_default_key_bindings(self):
        self.key_bindings = {**{
            "f1": self.help,
            "f11": self.toggle_full_screen,
            "r": self.reset_parameters,
            "w": self.save_images,
            "o": self.load_parameters,
            "e": self.save_parameters,
            "i": self.print_parameters,
            "q": self.close,
            "g": self.display_graph
        }, **self.key_bindings}

    def close(self):
        """close GUI"""
        self.app.quit()

    def reset_parameters(self):
        """reset sliders to default parameters"""
        super().reset_parameters()
        for widget_idx, ctrl in self.window.ctrl.items():
            ctrl.value = ctrl.value_default
        self.window.reset_sliders()

    def load_parameters(self):
        """import parameters dictionary from a yaml/json file on disk"""
        super().load_parameters()
        for widget_idx, widget in self.window.ctrl.items():
            matched = False
            for filtname, params in self.pipeline.parameters.items():
                for param_name in params.keys():
                    if param_name == widget.parameter_name_to_connect:
                        print(
                            f"MATCH & update {filtname} {widget_idx} with {self.pipeline.parameters[filtname][param_name]}")
                        self.window.ctrl[widget_idx].update(
                            self.pipeline.parameters[filtname][param_name])
                        matched = True
            assert matched, f"could not match widget {widget_idx} with parameter to connect {widget.parameter_name_to_connect}"
        print("------------")
        self.window.reset_sliders()

    def print_message(self, message_list: List[str]):
        print("\n".join(message_list))

    def toggle_full_screen(self):
        """toggle full screen"""
        if not hasattr(self, "full_screen_toggle"):
            self.full_screen_toggle = self.window.full_screen_flag
        self.full_screen_toggle = not self.full_screen_toggle
        if self.full_screen_toggle:
            # Go to fullscreen
            self.window.full_screen()
        else:
            window_size = self.window.size
            if window_size is not None and isinstance(window_size, str) and "full" in window_size.lower():
                # Special case where the window naturally goes to fullscreen since user defined it...
                # Force to go back to normal
                self.window.showNormal()
            else:  # Go back to normal size
                self.window.update_window()


class MainWindow(InteractivePipeWindow):
    def __init__(self, *args, controls=[], name="", pipeline: HeadlessPipeline = None, size=None, center=True, style=None, main_gui=None, **kwargs):
        InteractivePipeWindow.__init__(
            self, name=name, pipeline=pipeline, size=size)
        self.init_sliders(controls)
        self.size = size
        self.full_screen_flag = False
        self.pipeline = pipeline

        def run_fn(*args):
            all_keys = list(self.ctrl.keys())
            for idx in range(len(args)):
                self.ctrl[all_keys[idx]].update(args[idx])
            out = self.pipeline.run()
            flat_out = []
            for idx in range(len(out)):
                if isinstance(out[idx], list):
                    for idy in range(len(out[idx])):
                        logging.info(f"CONVERTING IMAGE  {idx} {idy}")
                        flat_out.append(self.convert_image(out[idx][idy]))
                else:
                    logging.info(f"CONVERTING IMAGE  {idx} ")
                    flat_out.append(self.convert_image(out[idx]))
            if out is None:
                logging.warning("No output to display")
                return  
            return tuple(flat_out)
        default_values = [self.ctrl[ctrl_key].value for ctrl_key in self.ctrl.keys()]
        io = gr.Interface(
            allow_flagging='never',
            fn=run_fn,
            title=self.name,
            inputs=self.widget_list,
            outputs=[gr.Image(), gr.Image(), gr.Image()],  # Need to match the output of the pipeline
            examples=[default_values],
            live=True,
            show_progress="minimal"
        )
        self.io = io

    @property
    def size(self):
        return self._size

    @size.setter
    def size(self, _size):
        if isinstance(_size, str):
            assert "full" in _size.lower() or "max" in _size.lower(
            ), f"size={_size} can only be among (full, fullscreen, maximized, max, maximum)"
        self._size = _size
        self.update_window()

    def update_window(self):
        pass

    def full_screen(self):
        pass

    def maximize_screen(self):
        pass

    def keyPressEvent(self, event):
        pass

    def init_sliders(self, controls: List[Control]):
        self.ctrl = {}
        self.result_label = {}
        self.name_label = {}
        self.widget_list = []
        control_factory = ControlFactory()
        for ctrl in controls:
            if isinstance(ctrl, Control):
                slider_instance = control_factory.create_control(
                    ctrl, self.update_parameter)
                control_widget = slider_instance.create()
                self.widget_list.append(control_widget)
            slider_name = ctrl.name
            self.ctrl[slider_name] = ctrl

            self.update_label(slider_name)

    def update_label(self, idx):
        val = self.ctrl[idx].value
        pass

    def update_parameter(self, idx, value):
        """Required implementation for graphical controllers update"""
        if self.ctrl[idx]._type == str:
            self.ctrl[idx].update(self.ctrl[idx].value_range[value])
        elif self.ctrl[idx]._type == bool:
            self.ctrl[idx].update(bool(value))
        elif self.ctrl[idx]._type == float:
            self.ctrl[idx].update(self.ctrl[idx].convert_int_to_value(value))
        elif self.ctrl[idx]._type == int:
            self.ctrl[idx].update(value)
        else:
            raise NotImplementedError("{self.ctrl[idx]._type} not supported")
        self.update_label(idx)
        self.refresh()

    def update_image(self, image_array_original, row, col):
        pass

    @staticmethod
    def convert_image(out_im):
        if isinstance(out_im, np.ndarray):
            return (out_im.clip(0., 1.) * 255).astype(np.uint8)
        else:
            return out_im

    def refresh(self):
        if self.pipeline is not None:
            self.io.launch()

    def reset_sliders(self):
        for widget_idx, ctrl in self.ctrl.items():
            if widget_idx in self.widget_list.keys():
                self.widget_list[widget_idx].reset()
            self.update_label(widget_idx)
        self.refresh()

    def add_image_placeholder(self, row, col):
        ax_placeholder = None
        text_label = None
        image_label = None
        self.image_canvas[row][col] = {
            "image": image_label, "title": text_label, "ax_placeholder": ax_placeholder}
