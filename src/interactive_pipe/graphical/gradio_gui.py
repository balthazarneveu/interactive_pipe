import logging
import math
from copy import copy
from typing import List, Optional

import gradio as gr
import numpy as np

from interactive_pipe.data_objects.audio import audio_to_html
from interactive_pipe.graphical.gradio_control import ControlFactory
from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.graphical.window import InteractivePipeWindow
from interactive_pipe.headless.control import Control
from interactive_pipe.headless.panel import Panel
from interactive_pipe.headless.pipeline import HeadlessPipeline

PYQTVERSION = None
MPL_SUPPORT = False
GRADIO_INTERFACE_MODE = False
try:
    import matplotlib.pyplot as plt

    from interactive_pipe.data_objects.curves import Curve
    from interactive_pipe.data_objects.table import Table

    MPL_SUPPORT = True
except ImportError:
    pass


class InteractivePipeGradio(InteractivePipeGUI):
    def init_app(self, **kwargs):
        self.window = MainWindow(
            controls=self.controls,
            name=self.name,
            pipeline=self.pipeline,
            size=self.size,
            main_gui=self,
            audio=self.audio,
            **kwargs,
        )
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
        if not self.pipeline._PipelineCore__initialized_inputs:
            raise RuntimeError("Did you forget to initialize the pipeline inputs?")
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
        # Iterate over rectangular image_canvas (not jagged out_list)
        # to ensure we create containers for all grid positions including padding
        for idx in range(len(self.window.image_canvas)):
            for idy in range(len(self.window.image_canvas[idx])):
                canvas_cell = self.window.image_canvas[idx][idy]
                # Handle None or uninitialized (float from np.empty) padding positions
                if canvas_cell is None or not isinstance(canvas_cell, dict):
                    out_list_gradio_containers.append(gr.HTML())
                    continue
                title = canvas_cell.get("title", f"{idx} {idy}")
                title = title.replace("_", " ")
                # Access out_list safely (it may be jagged/shorter than image_canvas)
                out_item = out_list[idx][idy] if idy < len(out_list[idx]) else None
                if out_item is None:
                    out_list_gradio_containers.append(gr.HTML())
                    continue
                if isinstance(out_item, np.ndarray):
                    if len(out_item.shape) == 1:
                        out_list_gradio_containers.append(gr.Audio(label=title))
                        canvas_cell["type"] = "audio"
                    else:
                        out_list_gradio_containers.append(gr.Image(format="png", type="numpy", label=title))
                        canvas_cell["type"] = "image"
                elif MPL_SUPPORT and isinstance(out_item, Curve):
                    # if out_item.title is not None:
                    #     title = out_item.title
                    out_list_gradio_containers.append(gr.Plot(label=title))
                    canvas_cell["type"] = "curve"
                elif isinstance(out_item, Table):
                    out_list_gradio_containers.append(gr.Dataframe(label=title))
                    canvas_cell["type"] = "table"
                # @TODO: https://github.com/balthazarneveu/interactive_pipe/issues/50 support audio!
                elif isinstance(out_item, str):
                    out_list_gradio_containers.append(gr.Textbox(label=title))
                else:
                    raise NotImplementedError(f"output type {type(out_item)} not supported")
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
    def __init__(
        self,
        *args,
        controls=None,
        name="",
        pipeline: Optional[HeadlessPipeline] = None,
        size=None,
        share_gradio_app=False,
        markdown_description=None,
        sliders_layout=None,
        sliders_per_row_layout=None,
        audio=False,
        audio_sampling_rate: int = 44100,
        **kwargs,
    ):
        if controls is None:
            controls = []
        InteractivePipeWindow.__init__(self, name=name, pipeline=pipeline, size=size)
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
            # Iterate over rectangular image_canvas to match container count
            for idx in range(len(self.image_canvas)):
                if isinstance(out[idx], list):
                    for idy in range(len(self.image_canvas[idx])):
                        # Handle jagged out list - may not have element at this position
                        if idy >= len(out[idx]) or out[idx][idy] is None:
                            flat_out.append("")
                        elif MPL_SUPPORT and isinstance(out[idx][idy], Curve):
                            # https://github.com/balthazarneveu/interactive_pipe/issues/54
                            # Update curves instead of creating new ones shall be faster
                            # Gradio still flickers anyway.
                            curve = out[idx][idy]
                            fig, ax = plt.subplots()
                            Curve._plot_curve(curve.data, ax=ax)
                            flat_out.append(fig)
                        elif isinstance(out[idx][idy], Table):
                            table = out[idx][idy]
                            # Convert to format expected by gr.Dataframe
                            # Format: list of lists with first row as headers
                            # Use _format_values() to apply precision formatting
                            # Check if this is a headerless table (all columns are empty)
                            has_headers = any(col != "" for col in table.columns)
                            if has_headers:
                                table_data = [table.columns] + table._format_values()
                            else:
                                # Headerless table - just show values
                                table_data = table._format_values()
                            flat_out.append(table_data)
                        elif isinstance(out[idx][idy], np.ndarray):
                            if len(out[idx][idy].shape) == 1:
                                logging.debug(f"CONVERTING AUDIO  {idx} {idy}")
                                flat_out.append((self.audio_sampling_rate, out[idx][idy]))
                            else:
                                logging.debug(f"CONVERTING IMAGE  {idx} {idy}")
                                flat_out.append(self.convert_image(out[idx][idy]))
                        elif isinstance(out[idx][idy], str):
                            flat_out.append(out[idx][idy])
                        else:
                            raise NotImplementedError(f"output type {type(out[idx][idy])} not suported")
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
            # Only process controls that have widgets (args only contains values for widgets)
            for idx in range(len(args)):
                if idx < len(self.ctrl_keys_with_widgets):
                    ctrl_key = self.ctrl_keys_with_widgets[idx]
                    self.ctrl[ctrl_key].update(args[idx])
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

        self.default_values = [self.ctrl[ctrl_key].value for ctrl_key in self.ctrl_keys_with_widgets]
        self.process_inputs_fn = process_inputs_fn
        self.run_fn = run_fn

    def instantiate_gradio_interface(self, outputs: List[gr.Blocks]):
        if GRADIO_INTERFACE_MODE:
            # Interface mode, high level wrapper
            # https://www.gradio.app/guides/the-interface-class
            self.io = gr.Interface(
                allow_flagging="never",
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

                # Group panels by position
                panels_by_position = self._group_panels_by_position()

                # Top panels
                if panels_by_position["top"]:
                    for panel in panels_by_position["top"]:
                        self._build_panel_widget(panel)

                # Middle section: left panels | images | right panels
                has_left = bool(panels_by_position["left"])
                has_right = bool(panels_by_position["right"])

                if has_left or has_right:
                    # Use Row layout when we have side panels
                    with gr.Row():
                        # Left panels column
                        if has_left:
                            with gr.Column(scale=1):
                                for panel in panels_by_position["left"]:
                                    self._build_panel_widget(panel)

                        # Images column (main content)
                        with gr.Column(scale=3):
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

                        # Right panels column
                        if has_right:
                            with gr.Column(scale=1):
                                for panel in panels_by_position["right"]:
                                    self._build_panel_widget(panel)
                else:
                    # No side panels - simple layout (backward compatibility)
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

                # Bottom panels (default) + ungrouped controls
                # Check if we have panels to render
                if hasattr(self, "root_panels") and self.root_panels:
                    # Panel-based rendering
                    # First render ungrouped controls
                    if self.ungrouped_controls:
                        with gr.Column():
                            for ctrl in self.ungrouped_controls:
                                widget = self._get_control_widget(ctrl)
                                if widget is not None:
                                    if isinstance(widget, list):
                                        # Handle button groups
                                        with gr.Row():
                                            for elem in widget:
                                                elem.render()
                                    else:
                                        widget.render()

                    # Then render bottom panel hierarchy
                    for panel in panels_by_position["bottom"]:
                        self._build_panel_widget(panel)
                else:
                    # Fall back to original flat rendering when no panels exist
                    if self.sliders_layout is None:
                        self.sliders_layout = "collapsible"
                    if self.sliders_per_row_layout is None:
                        self.sliders_per_row_layout = 1
                    if self.sliders_layout not in [
                        "compact",
                        "vertical",
                        "collapsible",
                        "smart",
                    ]:
                        raise ValueError(
                            f"sliders_layout must be one of "
                            f"['compact', 'vertical', 'collapsible', 'smart'], "
                            f"got {self.sliders_layout}"
                        )
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
                                for split_num in range(math.ceil(len(ctrl_indices) / self.sliders_per_row_layout)):
                                    with gr.Row():
                                        start = split_num * self.sliders_per_row_layout
                                        end = min(
                                            (split_num + 1) * self.sliders_per_row_layout,
                                            len(ctrl_indices),
                                        )
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
                        gr.Examples(
                            [self.default_values],
                            inputs=changing_inputs,
                            label="Presets",
                        )
                if self.markdown_description is not None:
                    title = "Description"
                    try:
                        if self.markdown_description.startswith("#"):
                            title = self.markdown_description.split("\n")[0][1:]
                    except Exception as _e:  # noqa E722
                        pass
                    with gr.Accordion(title, open=False):
                        gr.Markdown(self.markdown_description)
                io.load(fn=self.run_fn, inputs=changing_inputs, outputs=outputs)
                for idx in range(len(self.widget_list)):
                    if isinstance(self.widget_list[idx], list):
                        for idy, elem in enumerate(self.widget_list[idx]):
                            changing_inputs_copy = changing_inputs.copy()
                            ctrl_key = self.ctrl_keys_with_widgets[idx]
                            changing_inputs_copy[idx] = gr.State(self.ctrl[ctrl_key].value_range[idy])
                            elem.click(
                                fn=self.run_fn,
                                inputs=changing_inputs_copy,
                                outputs=outputs,
                                show_progress="minimal",
                            )
                    else:
                        self.widget_list[idx].change(
                            fn=self.run_fn,
                            inputs=changing_inputs,
                            outputs=outputs,
                            show_progress="minimal",
                        )

            self.io = io
        self.io.launch(share=self.share_gradio_app)

    def init_sliders(self, controls: List[Control]):
        self.ctrl = {}
        self.result_label = {}
        self.name_label = {}
        self.widget_list = []
        self.ctrl_keys_with_widgets = []  # Track which controls have widgets
        control_factory = ControlFactory()

        # Collect all panels and build hierarchy
        root_panels = set()  # Use set to avoid duplicates
        ungrouped_controls = []

        for ctrl in controls:
            if isinstance(ctrl, Control):
                self.ctrl[ctrl.name] = ctrl
                if ctrl.panel is None:
                    ungrouped_controls.append(ctrl)
                else:
                    # Find the root panel by traversing up the parent chain
                    root_panel = ctrl.panel.get_root()
                    root_panels.add(root_panel)

        # Store panel hierarchy for later rendering
        self.root_panels = list(root_panels)
        self.ungrouped_controls = ungrouped_controls

        # Create widgets for all controls (maintain flat list for event binding)
        for ctrl in controls:
            if isinstance(ctrl, Control):
                slider_instance = control_factory.create_control(ctrl, None)
                # Skip controls that return None (e.g., single-value controls)
                if slider_instance is None:
                    continue
                control_widget = slider_instance.create()
                self.widget_list.append(control_widget)
                self.ctrl_keys_with_widgets.append(ctrl.name)
            else:
                self.ctrl[ctrl.name] = ctrl

    def _get_control_widget(self, ctrl: Control):
        """Get the widget for a given control from widget_list."""
        if ctrl.name not in self.ctrl_keys_with_widgets:
            return None
        idx = self.ctrl_keys_with_widgets.index(ctrl.name)
        return self.widget_list[idx]

    def _group_panels_by_position(self) -> dict:
        """Group root panels by their position attribute.

        Returns:
            Dictionary with keys "top", "left", "right", "bottom" containing
            lists of panels for each position. Detached panels are excluded.
        """
        result = {"top": [], "left": [], "right": [], "bottom": []}
        if not hasattr(self, "root_panels"):
            return result
        for panel in self.root_panels:
            # Ignore detached panels (they open in separate windows)
            if panel.detached:
                continue
            pos = panel.position or "bottom"  # Default to bottom for backward compatibility
            if pos in result:
                result[pos].append(panel)
        return result

    def _build_panel_widget(self, panel: Panel):
        """Recursively build Gradio components for a Panel hierarchy.

        Args:
            panel: The Panel to build

        Returns:
            None (renders widgets in place using Gradio context managers)
        """
        # Determine if we need a container based on collapsible state
        if panel.collapsible:
            # Use Accordion for collapsible panels
            container = gr.Accordion(label=panel.name or "Group", open=not panel.collapsed)
        elif panel.name:
            # Use Column with a visible label/title for non-collapsible named panels
            # We'll use a Column and add the panel name as markdown
            container = gr.Column()
        else:
            # No name and not collapsible - just use a Column
            container = gr.Column()

        with container:
            # Add panel title for non-collapsible named panels (not using Accordion)
            if not panel.collapsible and panel.name:
                gr.Markdown(f"**{panel.name}**")

            # Determine layout based on elements structure
            if panel.elements and isinstance(panel.elements[0], list):
                # Grid layout: list of lists
                for row in panel.elements:
                    with gr.Row():
                        for element in row:
                            if isinstance(element, Panel):
                                self._build_panel_widget(element)
                            elif isinstance(element, Control):
                                widget = self._get_control_widget(element)
                                if widget is not None:
                                    if isinstance(widget, list):
                                        # Handle button groups
                                        with gr.Row():
                                            for elem in widget:
                                                elem.render()
                                    else:
                                        widget.render()
            elif panel.elements:
                # Vertical layout: flat list
                for element in panel.elements:
                    if isinstance(element, Panel):
                        self._build_panel_widget(element)
                    elif isinstance(element, Control):
                        widget = self._get_control_widget(element)
                        if widget is not None:
                            if isinstance(widget, list):
                                # Handle button groups
                                with gr.Row():
                                    for elem in widget:
                                        elem.render()
                            else:
                                widget.render()

            # Add controls assigned directly to this panel
            for ctrl in panel._controls:
                widget = self._get_control_widget(ctrl)
                if widget is not None:
                    if isinstance(widget, list):
                        # Handle button groups
                        with gr.Row():
                            for elem in widget:
                                elem.render()
                    else:
                        widget.render()

    @staticmethod
    def convert_image(out_im):
        if isinstance(out_im, np.ndarray):
            return (out_im.clip(0.0, 1.0) * 255).astype(np.uint8)
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
            "image": image_label,
            "title": text_label,
            "ax_placeholder": ax_placeholder,
        }

    def update_image(self, content, row, col):
        pass
