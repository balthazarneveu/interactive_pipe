import gradio as gr
import numpy as np
from typing import List
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.graphical.gradio_control import ControlFactory
from interactive_pipe.graphical.window import InteractivePipeWindow
from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.headless.control import Control
import logging
PYQTVERSION = None
MPL_SUPPORT = False
GRADIO_INTERFACE_MODE = False
try:
    from interactive_pipe.data_objects.curves import Curve
    import matplotlib.pyplot as plt
    MPL_SUPPORT = True
except ImportError:
    pass


class InteractivePipeGradio(InteractivePipeGUI):
    def init_app(self, **kwargs):
        self.window = MainWindow(controls=self.controls, name=self.name,
                                 pipeline=self.pipeline, size=self.size, main_gui=self, **kwargs)
        self.pipeline.global_params["__pipeline"] = self.pipeline
        # self.set_default_key_bindings()

    def run(self) -> list:
        assert self.pipeline._PipelineCore__initialized_inputs, "Did you forget to initialize the pipeline inputs?"
        out_list = self.window.process_inputs_fn(*self.window.default_values)
        out_list_gradio_containers = []
        for idx in range(len(out_list)):
            for idy in range(len(out_list[idx])):
                if isinstance(out_list[idx][idy], np.ndarray):
                    out_list_gradio_containers.append(gr.Image())
                elif MPL_SUPPORT and isinstance(out_list[idx][idy], Curve):
                    out_list_gradio_containers.append(gr.Plot())
                else:
                    raise NotImplementedError(
                        f"output type {type(out_list[idx][idy])} not supported")
        self.window.instantiate_gradio_interface(out_list_gradio_containers)
        self.window.refresh()
        self.custom_end()
        return self.pipeline.results

    def print_message(self, message_list: List[str]):
        print("\n".join(message_list))


class MainWindow(InteractivePipeWindow):
    def __init__(self, *args, controls=[], name="", pipeline: HeadlessPipeline = None, size=None, share_gradio_app=False, **kwargs):
        InteractivePipeWindow.__init__(
            self, name=name, pipeline=pipeline, size=size)
        self.init_sliders(controls)
        self.size = size
        self.full_screen_flag = False
        self.pipeline = pipeline
        self.share_gradio_app = share_gradio_app
        # Define the functions that will be called when the input changes for gradio. => gr.Interface(fn=process_fn)

        def process_outputs_fn(out) -> tuple:
            flat_out = []
            for idx in range(len(out)):
                if isinstance(out[idx], list):
                    for idy in range(len(out[idx])):
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

        def process_inputs_fn(*args) -> list:
            all_keys = list(self.ctrl.keys())
            for idx in range(len(args)):
                self.ctrl[all_keys[idx]].update(args[idx])
            out = self.pipeline.run()
            return out

        def run_fn(*args) -> tuple:
            out = process_inputs_fn(*args)
            out_tuple = process_outputs_fn(out)
            return out_tuple
        self.default_values = [self.ctrl[ctrl_key].value for ctrl_key in self.ctrl.keys()]
        self.process_inputs_fn = process_inputs_fn
        self.run_fn = run_fn

    def instantiate_gradio_interface(self, outputs: List[gr.Blocks]):
        if GRADIO_INTERFACE_MODE:
            # Interface mode, high level wrapper
            # https://www.gradio.app/guides/the-interface-class
            self.io = gr.Interface(
                allow_flagging='never',
                fn=self.run_fn,
                title=self.name,
                inputs=self.widget_list,
                outputs=outputs,
                examples=[self.default_values],
                live=True,
                show_progress="minimal",
                clear_btn=None,
            )
        else:
            # Gradio Blocks mode
            # https://www.gradio.app/guides/blocks-and-event-listeners
            with gr.Blocks() as io:
                with gr.Row():
                    for elem in outputs:
                        elem.render()
                with gr.Row():
                    for elem in self.widget_list:
                        with gr.Row():
                            elem.render()
                with gr.Row():
                    gr.Examples([self.default_values], inputs=self.widget_list)
                io.load(fn=self.run_fn, inputs=self.widget_list, outputs=outputs)
                for idx in range(len(self.widget_list)):
                    self.widget_list[idx].change(
                        fn=self.run_fn, inputs=self.widget_list,
                        outputs=outputs,
                        show_progress="minimal"
                    )
            self.io = io
        self.io.launch(share=self.share_gradio_app)

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
