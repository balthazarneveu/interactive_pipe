import gradio as gr
import numpy as np
import math
from typing import List
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.graphical.gradio_control import ControlFactory
from interactive_pipe.graphical.window import InteractivePipeWindow
from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.headless.control import Control
from interactive_pipe.data_objects.audio import audio_to_html
from copy import copy
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
                                 pipeline=self.pipeline, size=self.size, main_gui=self, audio=self.audio, **kwargs)
        self.pipeline.global_params["__pipeline"] = self.pipeline
        if self.audio:
            self.pipeline.global_params["__set_audio"] = self.__set_audio
            self.pipeline.global_params["__play"] = self.__play
            self.pipeline.global_params["__stop"] = self.__stop
            self.pipeline.global_params["__pause"] = self.__pause
            self.__set_audio(None)

    def __set_audio(self, audio_content):
        self.window.audio_content = audio_content

    def __play(self):
        pass

    def __pause(self):
        self.__set_audio(None)

    def __stop(self):
        self.__set_audio(None)

    def run(self) -> list:
        assert self.pipeline._PipelineCore__initialized_inputs, "Did you forget to initialize the pipeline inputs?"
        # In gradio, the first run is a "dry run", used to get the output types...
        try:
            global_params_first_run = copy(self.pipeline.global_params)
            # Do not use deepcopy, it will break the audio playback feature
        except Exception as exc:
            logging.warning(f"Cannot copy global_params: {exc}")
            global_params_first_run = self.pipeline.global_params
            pass
        out_list = self.window.process_inputs_fn(*self.window.default_values)
        self.pipeline.global_params = global_params_first_run
        # Reset global parameters... in case they were modified by the first run
        self.pipeline._reset_global_params()
        self.pipeline.reset_cache()
        self.window.refresh_display(out_list)
        out_list_gradio_containers = []
        for idx in range(len(out_list)):
            for idy in range(len(out_list[idx])):
                if self.window.image_canvas[idx][idy] is None:
                    out_list_gradio_containers.append(gr.HTML())
                    continue
                title = self.window.image_canvas[idx][idy].get("title", f"{idx} {idy}")
                title = title.replace("_", " ")
                if isinstance(out_list[idx][idy], np.ndarray):
                    if len(out_list[idx][idy].shape) == 1:
                        out_list_gradio_containers.append(gr.Audio(label=title))
                        self.window.image_canvas[idx][idy]["type"] = "audio"
                    else:
                        out_list_gradio_containers.append(gr.Image(format="png", type="numpy", label=title))
                        self.window.image_canvas[idx][idy]["type"] = "image"
                elif MPL_SUPPORT and isinstance(out_list[idx][idy], Curve):
                    # if out_list[idx][idy].title is not None:
                    #     title = out_list[idx][idy].title
                    out_list_gradio_containers.append(gr.Plot(label=title))
                    self.window.image_canvas[idx][idy]["type"] = "curve"
                # @TODO: https://github.com/balthazarneveu/interactive_pipe/issues/50 support audio!
                else:
                    raise NotImplementedError(
                        f"output type {type(out_list[idx][idy])} not supported")
        if self.window.audio:
            self.window.audio = gr.HTML()
            self.pipeline.global_params["__audio"] = self.window.audio
        self.window.instantiate_gradio_interface(out_list_gradio_containers)
        self.window.refresh()
        self.custom_end()
        return self.pipeline.results

    def print_message(self, message_list: List[str]):
        print("\n".join(message_list))


class MainWindow(InteractivePipeWindow):
    def __init__(self, *args, controls=[], name="", pipeline: HeadlessPipeline = None, size=None, share_gradio_app=False, markdown_description=None, sliders_layout=None, sliders_per_row_layout=None, audio=False, audio_sampling_rate: int = 44100, **kwargs):
        InteractivePipeWindow.__init__(
            self, name=name, pipeline=pipeline, size=size)
        self.markdown_description = markdown_description
        self.sliders_layout = sliders_layout
        self.sliders_per_row_layout = sliders_per_row_layout
        self.init_sliders(controls)
        self.size = size
        self.full_screen_flag = False
        self.pipeline = pipeline
        self.share_gradio_app = share_gradio_app
        self.audio = audio
        self.audio_sampling_rate = audio_sampling_rate
        # Define the functions that will be called when the input changes for gradio. => gr.Interface(fn=process_fn)

        def process_outputs_fn(out) -> tuple:
            flat_out = []
            for idx in range(len(out)):
                if isinstance(out[idx], list):
                    for idy in range(len(out[idx])):
                        if out[idx][idy] is None:
                            flat_out.append("")
                        elif MPL_SUPPORT and isinstance(out[idx][idy], Curve):
                            # https://github.com/balthazarneveu/interactive_pipe/issues/54
                            # Update curves instead of creating new ones shall be faster
                            # Gradio still flickers anyway.
                            curve = out[idx][idy]
                            fig, ax = plt.subplots()
                            Curve._plot_curve(curve.data, ax=ax)
                            flat_out.append(fig)
                        elif isinstance(out[idx][idy], np.ndarray):
                            if len(out[idx][idy].shape) == 1:
                                logging.debug(f"CONVERTING AUDIO  {idx} {idy}")
                                flat_out.append((self.audio_sampling_rate, out[idx][idy]))
                            else:
                                logging.debug(f"CONVERTING IMAGE  {idx} {idy}")
                                flat_out.append(self.convert_image(out[idx][idy]))
                        else:
                            raise NotImplementedError(
                                f"output type {type(out[idx][idy])} not suported")
                else:
                    logging.info(f"CONVERTING IMAGE  {idx} ")
                    flat_out.append(self.convert_image(out[idx]))
            if len(flat_out) == 1:
                return flat_out[0]
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
            if self.audio:
                html_audio = audio_to_html(self.audio_content)
                if isinstance(out_tuple, tuple):
                    return *out_tuple, html_audio
                else:
                    return out_tuple, html_audio
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
                with gr.Row(variant="compact"):
                    gr.Markdown("### " + self.name.replace("_", " "))
                for idy in range(len(self.image_canvas)):
                    with gr.Row():
                        for idx in range(len(self.image_canvas[idy])):
                            elem = outputs[idy * len(self.image_canvas[idy]) + idx]
                            if elem is not None:
                                elem.render()

                if self.audio:
                    outputs.append(self.audio)
                    with gr.Row():
                        self.audio.render()

                if self.sliders_layout is None:
                    self.sliders_layout = "collapsible"
                if self.sliders_per_row_layout is None:
                    self.sliders_per_row_layout = 1
                assert self.sliders_layout in ["compact", "vertical", "collapsible", "smart"]
                ctrl_dict_by_type = {"all": list(range(len(self.ctrl)))}
                categories = ["all"]
                if self.sliders_layout == "compact":
                    selected_mode = gr.Row()
                elif self.sliders_layout == "vertical":
                    # Use Column to stack elements vertically
                    selected_mode = gr.Column()
                elif self.sliders_layout == "collapsible":
                    selected_mode = gr.Accordion("Parameters", open=True)
                elif self.sliders_layout == "smart":
                    # Group sliders by type
                    ctrl_dict_by_type = {}
                    for ctrl_index, ctrl_key in enumerate(self.ctrl.keys()):
                        ctrl_type = self.ctrl[ctrl_key]._type
                        ctrl_type = str(ctrl_type).split("<class '")[1].replace("'>", "")
                        if ctrl_type == "int":
                            ctrl_type = "float"
                        if ctrl_type not in ctrl_dict_by_type:
                            ctrl_dict_by_type[ctrl_type] = []
                        ctrl_dict_by_type[ctrl_type].append(ctrl_index)
                    categories = ["str", "bool", "float"]
                    selected_mode = gr.Column()
                else:
                    raise NotImplementedError(f"Sliders layout {self.sliders_layout} not supported")
                for ctrl_type in categories:
                    ctrl_indices = ctrl_dict_by_type.get(ctrl_type, [])
                    if len(ctrl_indices) == 0:
                        continue
                    if self.sliders_per_row_layout == 1:
                        with selected_mode:
                            for idx in range(len(self.widget_list)):
                                if isinstance(self.widget_list[idx], list):
                                    with gr.Row():
                                        for elem in self.widget_list[idx]:
                                            elem.render()
                                else:
                                    elem = self.widget_list[idx]
                                    elem.render()
                    else:
                        with selected_mode:
                            for split_num in range(math.ceil(len(ctrl_indices)/self.sliders_per_row_layout)):
                                with gr.Row():
                                    start = split_num*self.sliders_per_row_layout
                                    end = min((split_num+1)*self.sliders_per_row_layout, len(ctrl_indices))
                                    for idx in ctrl_indices[start:end]:
                                        elem = self.widget_list[idx]
                                        elem.render()
                changing_inputs = []
                discard_reset_button = False
                for idx in range(len(self.widget_list)):
                    if isinstance(self.widget_list[idx], list):
                        changing_inputs.append(gr.State(self.ctrl[list(self.ctrl.keys())[idx]].value_default))
                        discard_reset_button = True  # Do not show reset button if there are lists of buttons
                        self.ctrl[list(self.ctrl.keys())[idx]].filter_to_connect.cache = False
                        self.ctrl[list(self.ctrl.keys())[idx]].filter_to_connect.cache_mem = None
                    else:
                        changing_inputs.append(self.widget_list[idx])
                if not discard_reset_button:
                    with gr.Accordion("Reset to default values", open=False):
                        gr.Examples([self.default_values], inputs=changing_inputs, label="Presets")
                if self.markdown_description is not None:
                    title = "Description"
                    try:
                        if self.markdown_description.startswith("#"):
                            title = self.markdown_description.split("\n")[0][1:]
                    except Exception as _e:
                        pass
                    with gr.Accordion(title, open=False):
                        gr.Markdown(self.markdown_description)
                io.load(fn=self.run_fn, inputs=changing_inputs, outputs=outputs)
                for idx in range(len(self.widget_list)):
                    if isinstance(self.widget_list[idx], list):
                        for idy, elem in enumerate(self.widget_list[idx]):
                            changing_inputs_copy = changing_inputs.copy()
                            changing_inputs_copy[idx] = gr.State(
                                self.ctrl[list(self.ctrl.keys())[idx]].value_range[idy])
                            elem.click(
                                fn=self.run_fn,
                                inputs=changing_inputs_copy,
                                outputs=outputs,
                                show_progress="minimal"
                            )
                    else:
                        self.widget_list[idx].change(
                            fn=self.run_fn,
                            inputs=changing_inputs,
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
        text_label = self.get_current_style(row, col).get("title", "")
        image_label = None
        self.image_canvas[row][col] = {
            "image": image_label, "title": text_label, "ax_placeholder": ax_placeholder}

    def update_image(self, content, row, col):
        pass
