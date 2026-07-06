"""Blocks-mode layout rendering for the gradio GUI backend.

Every function takes the window and renders inside the caller's gr.Blocks
context; all mutable state (ctrl, widget_list, sliders_layout defaults)
lives on the window.
"""

import math
from typing import TYPE_CHECKING

import gradio as gr

from interactive_pipe.headless.control import Control
from interactive_pipe.headless.panel import Panel

if TYPE_CHECKING:
    from interactive_pipe.graphical.gradio_gui import MainWindow


def group_panels_by_position(window: "MainWindow") -> dict:
    """Group root panels by their position attribute.

    Returns:
        Dictionary with keys "top", "left", "right", "bottom" containing
        lists of panels for each position. Detached panels are excluded.
    """
    result = {"top": [], "left": [], "right": [], "bottom": []}
    if not hasattr(window, "root_panels"):
        return result
    for panel in window.root_panels:
        # Ignore detached panels (they open in separate windows)
        if panel.detached:
            continue
        pos = panel.position or "bottom"  # Default to bottom for backward compatibility
        if pos in result:
            result[pos].append(panel)
    return result


def get_control_widget(window: "MainWindow", ctrl: Control):
    """Get the widget for a given control from the window's widget_list."""
    if ctrl.name not in window.ctrl_keys_with_widgets:
        return None
    idx = window.ctrl_keys_with_widgets.index(ctrl.name)
    return window.widget_list[idx]


def _render_widget(widget) -> None:
    """Render a single widget or a button group (list of widgets)."""
    if isinstance(widget, list):
        # Handle button groups
        with gr.Row():
            for elem in widget:
                elem.render()
    else:
        widget.render()


def build_panel_widget(window: "MainWindow", panel: Panel) -> None:
    """Recursively build Gradio components for a Panel hierarchy.

    Renders widgets in place using Gradio context managers.
    """
    # Determine if we need a container based on collapsible state
    if panel.collapsible:
        # Use Accordion for collapsible panels
        container = gr.Accordion(label=panel.name or "Group", open=not panel.collapsed)
    else:
        # Use a Column; named panels get their title as markdown below
        container = gr.Column()

    with container:
        # Add panel title for non-collapsible named panels (not using Accordion)
        if not panel.collapsible and panel.name:
            gr.Markdown(f"**{panel.name}**")

        # Determine layout based on elements structure
        if panel.elements and isinstance(panel.elements[0], list):
            # Grid layout: list of lists
            for row in panel.elements:  # type: ignore[reportGeneralTypeIssues]
                if isinstance(row, list):
                    with gr.Row():
                        for element in row:
                            if isinstance(element, Panel):
                                build_panel_widget(window, element)
                            elif isinstance(element, Control):
                                widget = get_control_widget(window, element)
                                if widget is not None:
                                    _render_widget(widget)
        elif panel.elements:
            # Vertical layout: flat list
            for element in panel.elements:
                if isinstance(element, Panel):
                    build_panel_widget(window, element)
                elif isinstance(element, Control):
                    widget = get_control_widget(window, element)
                    if widget is not None:
                        _render_widget(widget)

        # Add controls assigned directly to this panel
        for ctrl in panel._controls:
            widget = get_control_widget(window, ctrl)
            if widget is not None:
                _render_widget(widget)


def render_image_grid(window: "MainWindow", outputs: list) -> None:
    """Render the output containers as a row-major grid plus the audio widget.

    Appends the audio HTML widget to `outputs` when audio mode is on (the
    event bindings need it in the outputs list).
    """
    if window.image_canvas is not None:
        for idy in range(len(window.image_canvas)):  # type: ignore[reportArgumentType]
            if window.image_canvas[idy] is None:
                continue
            with gr.Row():
                for idx in range(len(window.image_canvas[idy])):  # type: ignore[reportOptionalSubscript]
                    elem = outputs[idy * len(window.image_canvas[idy]) + idx]  # type: ignore[reportOptionalSubscript]
                    if elem is not None:
                        elem.render()  # type: ignore[reportAttributeAccessIssue]

    if window.audio:
        if hasattr(window, "audio_widget") and isinstance(window.audio_widget, gr.HTML):
            outputs.append(window.audio_widget)
            with gr.Row():
                window.audio_widget.render()  # type: ignore[reportAttributeAccessIssue]


def render_bottom_controls(window: "MainWindow", panels_by_position: dict) -> None:
    """Render ungrouped controls then the bottom panel hierarchy."""
    if window.ungrouped_controls:
        with gr.Column():
            for ctrl in window.ungrouped_controls:
                widget = get_control_widget(window, ctrl)
                if widget is not None:
                    _render_widget(widget)

    for panel in panels_by_position["bottom"]:  # type: ignore[reportGeneralTypeIssues]
        build_panel_widget(window, panel)


def render_flat_sliders(window: "MainWindow") -> None:
    """Fallback flat slider rendering when no panels exist.

    Supports the compact/vertical/collapsible/smart layouts and the
    sliders_per_row_layout splitting. Mutates the window's layout defaults
    (sliders_layout/sliders_per_row_layout).
    """
    if window.sliders_layout is None:
        window.sliders_layout = "collapsible"
    if window.sliders_per_row_layout is None:
        window.sliders_per_row_layout = 1
    if window.sliders_layout not in [
        "compact",
        "vertical",
        "collapsible",
        "smart",
    ]:
        raise ValueError(
            f"sliders_layout must be one of "
            f"['compact', 'vertical', 'collapsible', 'smart'], "
            f"got {window.sliders_layout}"
        )
    ctrl_dict_by_type = {"all": list(range(len(window.ctrl)))}
    categories = ["all"]
    if window.sliders_layout == "compact":
        selected_mode = gr.Row()
    elif window.sliders_layout == "vertical":
        # Use Column to stack elements vertically
        selected_mode = gr.Column()
    elif window.sliders_layout == "collapsible":
        selected_mode = gr.Accordion("Parameters", open=True)
    elif window.sliders_layout == "smart":
        # Group sliders by type
        ctrl_dict_by_type = {}
        for ctrl_index, ctrl_key in enumerate(window.ctrl.keys()):
            ctrl_type = window.ctrl[ctrl_key]._type
            ctrl_type = str(ctrl_type).split("<class '")[1].replace("'>", "")
            if ctrl_type == "int":
                ctrl_type = "float"
            if ctrl_type not in ctrl_dict_by_type:
                ctrl_dict_by_type[ctrl_type] = []
            ctrl_dict_by_type[ctrl_type].append(ctrl_index)
        categories = ["str", "bool", "float"]
        selected_mode = gr.Column()
    else:
        raise NotImplementedError(f"Sliders layout {window.sliders_layout} not supported")
    for ctrl_type in categories:
        ctrl_indices = ctrl_dict_by_type.get(ctrl_type, [])
        if len(ctrl_indices) == 0:
            continue
        if window.sliders_per_row_layout == 1:
            with selected_mode:
                for idx in range(len(window.widget_list)):
                    if isinstance(window.widget_list[idx], list):
                        with gr.Row():
                            for elem in window.widget_list[idx]:
                                elem.render()
                    else:
                        elem = window.widget_list[idx]
                        elem.render()
        else:
            with selected_mode:
                for split_num in range(math.ceil(len(ctrl_indices) / window.sliders_per_row_layout)):
                    with gr.Row():
                        start = split_num * window.sliders_per_row_layout
                        end = min(
                            (split_num + 1) * window.sliders_per_row_layout,
                            len(ctrl_indices),
                        )
                        for idx in ctrl_indices[start:end]:
                            elem = window.widget_list[idx]
                            elem.render()


def collect_changing_inputs(window: "MainWindow") -> tuple:
    """Assemble the event-binding inputs list.

    Button groups become gr.State placeholders and disable their filter's
    cache. Returns (changing_inputs, discard_reset_button).
    """
    changing_inputs = []
    discard_reset_button = False
    for idx in range(len(window.widget_list)):
        if isinstance(window.widget_list[idx], list):
            changing_inputs.append(gr.State(window.ctrl[list(window.ctrl.keys())[idx]].value_default))
            discard_reset_button = True  # Do not show reset button if there are lists of buttons
            window.ctrl[list(window.ctrl.keys())[idx]].filter_to_connect.cache = False
            window.ctrl[list(window.ctrl.keys())[idx]].filter_to_connect.cache_mem = None
        else:
            changing_inputs.append(window.widget_list[idx])
    return changing_inputs, discard_reset_button


def render_reset_and_description(window: "MainWindow", changing_inputs: list, discard_reset_button: bool) -> None:
    """Render the reset-presets accordion and the markdown description."""
    if not discard_reset_button:
        with gr.Accordion("Reset to default values", open=False):
            gr.Examples(
                [window.default_values],
                inputs=changing_inputs,
                label="Presets",
            )
    if window.markdown_description is not None:
        title = "Description"
        try:
            if window.markdown_description.startswith("#"):
                title = window.markdown_description.split("\n")[0][1:]
        except AttributeError:
            # markdown_description is not a str: keep default title
            pass
        with gr.Accordion(title, open=False):
            gr.Markdown(window.markdown_description)


def bind_events(window: "MainWindow", io, changing_inputs: list, outputs: list) -> None:
    """Wire initial load plus per-widget change/click events to run_fn."""
    io.load(fn=window.run_fn, inputs=changing_inputs, outputs=outputs)
    for idx in range(len(window.widget_list)):
        if isinstance(window.widget_list[idx], list):
            for idy, elem in enumerate(window.widget_list[idx]):
                changing_inputs_copy = changing_inputs.copy()
                ctrl_key = window.ctrl_keys_with_widgets[idx]
                changing_inputs_copy[idx] = gr.State(window.ctrl[ctrl_key].value_range[idy])
                elem.click(
                    fn=window.run_fn,
                    inputs=changing_inputs_copy,
                    outputs=outputs,
                    show_progress="minimal",
                )
        else:
            window.widget_list[idx].change(
                fn=window.run_fn,
                inputs=changing_inputs,
                outputs=outputs,
                show_progress="minimal",
            )
