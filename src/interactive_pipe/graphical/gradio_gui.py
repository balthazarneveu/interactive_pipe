import logging
from copy import copy
from typing import List, Optional

import gradio as gr
import numpy as np

from interactive_pipe.data_objects.audio import audio_to_html
from interactive_pipe.graphical.gradio_control import ControlFactory
from interactive_pipe.graphical.gradio_layout import (
    bind_events,
    build_panel_widget,
    collect_changing_inputs,
    get_control_widget,
    group_panels_by_position,
    render_bottom_controls,
    render_flat_sliders,
    render_image_grid,
    render_reset_and_description,
)
from interactive_pipe.graphical.gradio_outputs import (  # noqa: F401
    MPL_SUPPORT,  # re-exported for backward compatibility
    build_output_container,
    convert_output_value,
)
from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.graphical.window import InteractivePipeWindow
from interactive_pipe.headless.control import Control
from interactive_pipe.headless.panel import Panel
from interactive_pipe.headless.pipeline import HeadlessPipeline

GRADIO_INTERFACE_MODE = False


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
        if self.audio:
            audio_bindings = self.pipeline.framework_state.audio
            audio_bindings.set_audio = self.__set_audio
            audio_bindings.play = self.__play
            audio_bindings.stop = self.__stop
            audio_bindings.pause = self.__pause
            self.__set_audio(None)

    def __set_audio(self, audio_content):
        if not hasattr(self.window, "audio_content"):
            self.window.audio_content = None  # type: ignore[reportAttributeAccessIssue]
        self.window.audio_content = audio_content  # type: ignore[reportAttributeAccessIssue]

    def __play(self):
        pass

    def __pause(self):
        self.__set_audio(None)

    def __stop(self):
        self.__set_audio(None)

    def run(self) -> list:
        if not self.pipeline._PipelineCore__initialized_inputs:  # type: ignore[reportAttributeAccessIssue]
            raise RuntimeError("Did you forget to initialize the pipeline inputs?")
        # In gradio, the first run is a "dry run", used to get the output types...
        try:
            global_params_first_run = copy(self.pipeline.global_params)
            # Do not use deepcopy, it will break the audio playback feature
        except Exception as exc:
            # Broad on purpose: global_params can hold arbitrary user objects;
            # if the shallow copy fails, fall back to a shared reference.
            logging.warning(f"Cannot copy global_params: {exc}")
            global_params_first_run = self.pipeline.global_params
        out_list = self.window.process_inputs_fn(*self.window.default_values)
        self.pipeline.global_params = global_params_first_run
        # Reset global parameters... in case they were modified by the first run
        self.pipeline._reset_global_params()
        # framework_state is deliberately NOT rolled back: the dry run's
        # layout.style titles and layout.grid arrangement are its purpose.
        self.pipeline.reset_cache()
        self.window.refresh_display(out_list)
        out_list_gradio_containers = []
        # Iterate over rectangular image_canvas (not jagged out_list)
        # to ensure we create containers for all grid positions including padding
        if self.window.image_canvas is None:
            raise RuntimeError("image_canvas not initialized")
        for idx in range(len(self.window.image_canvas)):  # type: ignore[reportArgumentType]
            if self.window.image_canvas[idx] is None:
                continue
            for idy in range(len(self.window.image_canvas[idx])):  # type: ignore[reportOptionalSubscript]
                canvas_cell = self.window.image_canvas[idx][idy]  # type: ignore[reportOptionalSubscript]
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
                container, type_tag = build_output_container(out_item, title)
                out_list_gradio_containers.append(container)
                if type_tag is not None:
                    canvas_cell["type"] = type_tag
        if self.window.audio:
            audio_widget = gr.HTML()
            self.window.audio_widget = audio_widget  # type: ignore[reportAttributeAccessIssue]
        self.window.instantiate_gradio_interface(out_list_gradio_containers)
        self.window.refresh()
        self.custom_end()
        results = self.pipeline.results
        if results is None:
            return []
        if isinstance(results, tuple):
            return list(results)
        return results  # type: ignore[reportReturnType]

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
        self.audio_widget = None  # type: ignore[reportAttributeAccessIssue]
        self.default_values = [self.ctrl[ctrl_key].value for ctrl_key in self.ctrl_keys_with_widgets]
        # Aliases kept for compatibility: gradio event bindings and
        # InteractivePipeGradio.run reference these attribute names.
        self.process_inputs_fn = self.process_inputs
        self.run_fn = self.run_all

    def process_outputs(self, out) -> tuple:
        """Convert pipeline outputs to per-type gradio values (flat tuple)."""
        flat_out = []
        # Iterate over rectangular image_canvas to match container count
        if self.image_canvas is None:
            raise RuntimeError("image_canvas not initialized")
        if out is None:
            logging.warning("No output to display")
            return tuple()
        for idx in range(len(self.image_canvas)):  # type: ignore[reportArgumentType]
            if idx >= len(out) or out[idx] is None:
                continue
            if isinstance(out[idx], list):
                if self.image_canvas[idx] is None:
                    continue
                for idy in range(len(self.image_canvas[idx])):  # type: ignore[reportOptionalSubscript]
                    # Handle jagged out list - may not have element at this position
                    if idy >= len(out[idx]) or out[idx][idy] is None:
                        flat_out.append("")
                    else:
                        flat_out.append(
                            convert_output_value(
                                out[idx][idy],
                                audio_sampling_rate=self.audio_sampling_rate,
                                convert_image=self.convert_image,
                            )
                        )
            else:
                logging.info(f"CONVERTING IMAGE  {idx} ")
                flat_out.append(self.convert_image(out[idx]))
        if len(flat_out) == 1:
            return flat_out[0]
        return tuple(flat_out)

    def process_inputs(self, *args) -> list:
        """Update controls from widget values and run the pipeline."""
        # Only process controls that have widgets (args only contains values for widgets)
        for idx in range(len(args)):
            if idx < len(self.ctrl_keys_with_widgets):
                ctrl_key = self.ctrl_keys_with_widgets[idx]
                self.ctrl[ctrl_key].update(args[idx])
        if self.pipeline is None:
            raise RuntimeError("Pipeline is not set")
        out = self.pipeline.run()  # type: ignore[reportOptionalMemberAccess]
        if out is None:
            return []
        if isinstance(out, tuple):
            return list(out)
        return out  # type: ignore[reportReturnType]

    def run_all(self, *args) -> tuple:
        """Full widget-values -> pipeline -> gradio-values round trip."""
        out = self.process_inputs(*args)
        out_tuple = self.process_outputs(out)
        if self.audio:
            audio_content = getattr(self, "audio_content", None)
            html_audio = audio_to_html(audio_content)  # type: ignore[reportOptionalMemberAccess]
            if isinstance(out_tuple, tuple):
                return (*out_tuple, html_audio)
            else:
                return (out_tuple, html_audio)
        return out_tuple

    def instantiate_gradio_interface(self, outputs: List[gr.components.Component]):  # type: ignore[reportInvalidTypeForm]
        """Build the interface then launch it (kept as build + launch wrapper)."""
        self.build_interface(outputs)
        self.launch()

    def build_interface(self, outputs: List[gr.components.Component]):  # type: ignore[reportInvalidTypeForm]
        """Construct self.io without launching (tests can build headlessly)."""
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
            return
        # Gradio Blocks mode
        # https://www.gradio.app/guides/blocks-and-event-listeners
        with gr.Blocks() as io:
            with gr.Row(variant="compact"):
                name_display = (self.name or "").replace("_", " ")  # type: ignore[reportOptionalMemberAccess]
                gr.Markdown("### " + name_display)

            # Group panels by position
            panels_by_position = self._group_panels_by_position()

            # Top panels
            for panel in panels_by_position["top"]:  # type: ignore[reportGeneralTypeIssues]
                self._build_panel_widget(panel)

            # Middle section: left panels | images | right panels
            has_left = bool(panels_by_position["left"])
            has_right = bool(panels_by_position["right"])

            if has_left or has_right:
                # Use Row layout when we have side panels
                with gr.Row():
                    if has_left:
                        with gr.Column(scale=1):
                            for panel in panels_by_position["left"]:  # type: ignore[reportGeneralTypeIssues]
                                self._build_panel_widget(panel)

                    # Images column (main content)
                    with gr.Column(scale=3):
                        render_image_grid(self, outputs)

                    if has_right:
                        with gr.Column(scale=1):
                            for panel in panels_by_position["right"]:  # type: ignore[reportGeneralTypeIssues]
                                self._build_panel_widget(panel)
            else:
                # No side panels - simple layout (backward compatibility)
                render_image_grid(self, outputs)

            # Bottom panels (default) + ungrouped controls
            if hasattr(self, "root_panels") and self.root_panels:
                render_bottom_controls(self, panels_by_position)
            else:
                # Fall back to original flat rendering when no panels exist
                render_flat_sliders(self)

            changing_inputs, discard_reset_button = collect_changing_inputs(self)
            render_reset_and_description(self, changing_inputs, discard_reset_button)
            bind_events(self, io, changing_inputs, outputs)

        self.io = io

    def launch(self):
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
        """Get the widget for a given control. Delegates to gradio_layout."""
        return get_control_widget(self, ctrl)

    def _group_panels_by_position(self) -> dict:
        """Group root panels by position. Delegates to gradio_layout."""
        return group_panels_by_position(self)

    def _build_panel_widget(self, panel: Panel):
        """Recursively render a Panel hierarchy. Delegates to gradio_layout."""
        return build_panel_widget(self, panel)

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
        if self.image_canvas is None:
            raise RuntimeError("image_canvas not initialized")
        if self.image_canvas[row] is None:
            raise RuntimeError(f"image_canvas row {row} not initialized")
        self.image_canvas[row][col] = {  # type: ignore[reportOptionalSubscript]
            "image": image_label,
            "title": text_label,
            "ax_placeholder": ax_placeholder,
        }

    def update_image(self, content, row, col):
        pass
