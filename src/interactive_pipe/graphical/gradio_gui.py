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
try:
    from interactive_pipe.data_objects.curves import Curve
    import matplotlib.pyplot as plt
    MPL_SUPPORT = True
except ImportError:
    pass


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
        # self.set_default_key_bindings()

    def run(self) -> list:
        assert self.pipeline._PipelineCore__initialized_inputs, "Did you forget to initialize the pipeline inputs?"
        _out_tuple = self.window.run_fn(*self.window.default_values)
        self.window.instantiate_gradio_interface()
        self.window.refresh()
        self.custom_end()
        return self.pipeline.results

    def print_message(self, message_list: List[str]):
        print("\n".join(message_list))


class MainWindow(InteractivePipeWindow):
    def __init__(self, *args, controls=[], name="", pipeline: HeadlessPipeline = None, size=None, center=True, style=None, main_gui=None, **kwargs):
        InteractivePipeWindow.__init__(
            self, name=name, pipeline=pipeline, size=size)
        self.init_sliders(controls)
        self.size = size
        self.full_screen_flag = False
        self.pipeline = pipeline

        def process_outputs_fn(out) -> tuple:
            flat_out = []
            for idx in range(len(out)):
                if isinstance(out[idx], list):
                    for idy in range(len(out[idx])):
                        print(out[idx][idy])
                        if MPL_SUPPORT and isinstance(out[idx][idy], Curve):
                            curve = out[idx][idy]
                            fig, ax = plt.subplots()
                            Curve._plot_curve(curve.data, ax=ax)
                            flat_out.append(fig)
                        elif isinstance(out[idx][idy], np.ndarray):
                            logging.info(f"CONVERTING IMAGE  {idx} {idy}")
                            flat_out.append(self.convert_image(out[idx][idy]))
                        else:
                            raise NotImplementedError(
                                f"output type {type(out[idx][idy])} not supported")
                else:
                    logging.info(f"CONVERTING IMAGE  {idx} ")
                    flat_out.append(self.convert_image(out[idx]))
            if out is None:
                logging.warning("No output to display")
                return
            return tuple(flat_out)

        def run_fn(*args) -> tuple:
            all_keys = list(self.ctrl.keys())
            for idx in range(len(args)):
                self.ctrl[all_keys[idx]].update(args[idx])
            out = self.pipeline.run()
            return process_outputs_fn(out)
        self.default_values = [self.ctrl[ctrl_key].value for ctrl_key in self.ctrl.keys()]

        self.run_fn = run_fn

    def instantiate_gradio_interface(self):
        io = gr.Interface(
            allow_flagging='never',
            fn=self.run_fn,
            title=self.name,
            inputs=self.widget_list,
            # outputs=[gr.Image(), gr.Image(), gr.Image()],  # Need to match the output of the pipeline
            # outputs=[gr.LinePlot(), gr.LinePlot()],
            outputs=[gr.Plot(), gr.Plot()],
            examples=[self.default_values],
            live=True,
            show_progress="minimal"
        )
        self.io = io

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
                    ctrl, None)
                control_widget = slider_instance.create()
                self.widget_list.append(control_widget)
            slider_name = ctrl.name
            self.ctrl[slider_name] = ctrl

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
        # Click on default examples in Gradio
        pass

    def add_image_placeholder(self, row, col):
        ax_placeholder = None
        text_label = None
        image_label = None
        self.image_canvas[row][col] = {
            "image": image_label, "title": text_label, "ax_placeholder": ax_placeholder}
