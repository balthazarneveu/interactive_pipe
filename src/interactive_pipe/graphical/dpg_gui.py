import logging
from typing import Any, List, Optional, cast

import numpy as np

from interactive_pipe.graphical.dpg_control import ControlFactory
from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.graphical.window import InteractivePipeWindow
from interactive_pipe.headless.control import Control, TimeControl
from interactive_pipe.headless.keyboard import KeyboardControl
from interactive_pipe.headless.panel import Panel
from interactive_pipe.headless.pipeline import HeadlessPipeline

DPG_AVAILABLE = False

try:
    import dearpygui.dearpygui as dpg

    DPG_AVAILABLE = True
except ImportError:
    dpg = None  # type: ignore[reportAssignmentType]
    logging.warning("DearPyGui not available. DPG backend will not work.")

# Check for Curve and Table support
try:
    from interactive_pipe.data_objects.curves import Curve, SingleCurve
    from interactive_pipe.data_objects.table import Table

    CURVE_SUPPORT = True
except ImportError:
    Curve = None  # type: ignore[reportAssignmentType]
    SingleCurve = None  # type: ignore[reportAssignmentType]
    Table = None  # type: ignore[reportAssignmentType]
    CURVE_SUPPORT = False


def _get_dpg_key_mapping_dict():
    """Return DPG key code mapping; only call when dpg is not None."""
    assert dpg is not None
    return {
        dpg.mvKey_F1: "f1",
        dpg.mvKey_F2: "f2",
        dpg.mvKey_F3: "f3",
        dpg.mvKey_F4: "f4",
        dpg.mvKey_F5: "f5",
        dpg.mvKey_F6: "f6",
        dpg.mvKey_F7: "f7",
        dpg.mvKey_F8: "f8",
        dpg.mvKey_F9: "f9",
        dpg.mvKey_F10: "f10",
        dpg.mvKey_F11: "f11",
        dpg.mvKey_F12: "f12",
        dpg.mvKey_Up: KeyboardControl.KEY_UP,
        dpg.mvKey_Down: KeyboardControl.KEY_DOWN,
        dpg.mvKey_Left: KeyboardControl.KEY_LEFT,
        dpg.mvKey_Right: KeyboardControl.KEY_RIGHT,
        dpg.mvKey_Prior: KeyboardControl.KEY_PAGEUP,
        dpg.mvKey_Next: KeyboardControl.KEY_PAGEDOWN,
        dpg.mvKey_Spacebar: KeyboardControl.KEY_SPACEBAR,
    }


class InteractivePipeDPG(InteractivePipeGUI):
    """Dear PyGui backend for interactive pipelines."""

    def init_app(self, **kwargs):
        if not DPG_AVAILABLE or dpg is None:
            raise ModuleNotFoundError(
                "DearPyGui is required for the DPG backend. Install it with: pip install interactive-pipe[dpg]"
            )
        assert dpg is not None
        dpg.create_context()

        self.window = MainWindow(
            controls=self.controls,
            name=self.name,
            pipeline=self.pipeline,
            size=self.size,
            main_gui=self,
            **kwargs,
        )

        self.pipeline.global_params["__pipeline"] = self.pipeline
        self.set_default_key_bindings()

    def run(self) -> list:
        if not self.pipeline._PipelineCore__initialized_inputs:  # type: ignore[reportAttributeAccessIssue]
            raise RuntimeError("Did you forget to initialize the pipeline inputs?")

        # Setup and show viewport
        if dpg is None:
            raise ModuleNotFoundError("DearPyGui is required")

        dpg.setup_dearpygui()
        dpg.show_viewport()

        # Initial refresh
        self.window.refresh()

        # Custom render loop with keyboard polling
        # This allows us to capture keys even when widgets have focus
        while dpg.is_dearpygui_running():
            # Poll keyboard shortcuts
            self._poll_keyboard_shortcuts()

            # Render frame
            dpg.render_dearpygui_frame()

        # Cleanup
        dpg.destroy_context()

        self.custom_end()
        results = self.pipeline.results
        if results is None:
            return []
        if isinstance(results, tuple):
            return list(results)
        return results  # type: ignore[reportReturnType]

    def set_default_key_bindings(self):
        self.key_bindings = {
            **{
                "f1": self.help,
                "f11": self.toggle_full_screen,
                "r": self.reset_parameters,
                "w": self.save_images,
                "o": self.load_parameters,
                "e": self.save_parameters,
                "i": self.print_parameters,
                "q": self.close,
                "g": self.display_graph,
            },
            **self.key_bindings,
        }

        # Map key bindings to DPG key codes for polling.
        # Include default shortcuts, a-z (for KeyboardControl e.g. keydown="d" keyup="u"),
        # and special keys (arrows, pageup/down, space) so all keyboard controls work.
        if dpg is not None:
            assert dpg is not None
            self._key_code_map = {
                dpg.mvKey_F1: "f1",
                dpg.mvKey_F11: "f11",
                dpg.mvKey_R: "r",
                dpg.mvKey_W: "w",
                dpg.mvKey_O: "o",
                dpg.mvKey_E: "e",
                dpg.mvKey_I: "i",
                dpg.mvKey_Q: "q",
                dpg.mvKey_G: "g",
            }
            # Letters a-z for KeyboardControl (e.g. keydown="d", keyup="u")
            for c in "abcdefghijklmnopqrstuvwxyz":
                dpg_key = getattr(dpg, f"mvKey_{c.upper()}", None)
                if dpg_key is not None:
                    self._key_code_map[dpg_key] = c
            # Special keys used by KeyboardControl (up, down, left, right, pageup, pagedown, space)
            special = [
                (dpg.mvKey_Up, KeyboardControl.KEY_UP),
                (dpg.mvKey_Down, KeyboardControl.KEY_DOWN),
                (dpg.mvKey_Left, KeyboardControl.KEY_LEFT),
                (dpg.mvKey_Right, KeyboardControl.KEY_RIGHT),
                (dpg.mvKey_Prior, KeyboardControl.KEY_PAGEUP),
                (dpg.mvKey_Next, KeyboardControl.KEY_PAGEDOWN),
                (dpg.mvKey_Spacebar, KeyboardControl.KEY_SPACEBAR),
            ]
            for dpg_key, key_str in special:
                self._key_code_map[dpg_key] = key_str
        else:
            self._key_code_map = {}

        # Track processed keys to avoid repeated execution
        self._processed_keys = set()

    def _poll_keyboard_shortcuts(self):
        """Poll keyboard state for shortcuts (called every frame)."""
        if dpg is None:
            return

        # Check each mapped key
        for key_code, key_str in self._key_code_map.items():
            if dpg.is_key_pressed(key_code):
                # Only process if not already handled this press
                if key_code not in self._processed_keys:
                    self._processed_keys.add(key_code)
                    logging.debug(f"Key pressed (polled): {key_str} (code={key_code})")

                    # Execute the bound function
                    if key_str in self.key_bindings:
                        self.key_bindings[key_str]()

                    # Also check context key bindings
                    for ctx_key, event_dict in self.context_key_bindings.items():
                        if ctx_key == key_str:
                            self.pipeline.global_params["__events"][event_dict["param_name"]] = True
                            logging.info(f"TRIGGERED A KEY EVENT {key_str} - {event_dict['doc']}")
                            self.pipeline.reset_cache()
                            if hasattr(self, "window"):
                                self.window.refresh()
                    self.reset_context_events()
            else:
                # Key released - remove from processed set
                self._processed_keys.discard(key_code)

    def toggle_full_screen(self):
        """toggle full screen"""
        if dpg is None:
            return
        if not hasattr(self, "full_screen_toggle"):
            self.full_screen_toggle = False
        self.full_screen_toggle = not self.full_screen_toggle
        if self.full_screen_toggle:
            dpg.toggle_viewport_fullscreen()
        else:
            dpg.toggle_viewport_fullscreen()

    def close(self):
        """Close GUI."""
        if dpg is not None:
            dpg.stop_dearpygui()

    def reset_parameters(self):
        """Reset sliders to default parameters."""
        super().reset_parameters()
        for widget_idx, ctrl in self.window.ctrl.items():
            if isinstance(ctrl, TimeControl):
                self.start_time = None  # Reset the timer
            ctrl.value = ctrl.value_default
        self.window.reset_sliders()

    def load_parameters(self):
        """Import parameters dictionary from a yaml/json file on disk."""
        super().load_parameters()
        for widget_idx, widget in self.window.ctrl.items():
            matched = False
            for filtname, params in self.pipeline.parameters.items():
                for param_name in params.keys():
                    if param_name == widget.parameter_name_to_connect:
                        logging.info(
                            f"MATCH & update {filtname} {widget_idx} with"
                            + f"{self.pipeline.parameters[filtname][param_name]}"
                        )
                        self.window.ctrl[widget_idx].update(self.pipeline.parameters[filtname][param_name])
                        matched = True
            if not matched:
                raise ValueError(
                    f"could not match widget {widget_idx} with parameter to connect {widget.parameter_name_to_connect}"
                )
        self.window.reset_sliders()

    def print_message(self, message_list: List[str]):
        """Print message to console and show DPG modal popup."""
        print("\n".join(message_list))
        self._show_modal_popup("\n".join(message_list))

    def _show_modal_popup(self, message: str):
        """Show a modal popup window with the message."""
        if dpg is None:
            return
        assert dpg is not None
        dpg_ref = dpg
        popup_tag = "help_popup"

        # Delete existing popup if present
        if dpg_ref.does_item_exist(popup_tag):
            dpg_ref.delete_item(popup_tag)

        # Create modal popup window
        with dpg_ref.window(
            label="Help",
            modal=True,
            tag=popup_tag,
            no_resize=True,
            autosize=True,
        ):
            dpg_ref.add_text(message)
            dpg_ref.add_button(label="Close", callback=lambda: dpg_ref.delete_item(popup_tag))


class MainWindow(InteractivePipeWindow):
    """Main window class for DPG backend."""

    # Key mapping from DPG key codes to string keys
    key_mapping_dict = _get_dpg_key_mapping_dict() if (DPG_AVAILABLE and dpg is not None) else {}

    def __init__(
        self,
        *args,
        controls=None,
        name="",
        pipeline: Optional[HeadlessPipeline] = None,
        size=None,
        center=True,
        style=None,
        main_gui=None,
        **kwargs,
    ):
        if controls is None:
            controls = []
        if not DPG_AVAILABLE or dpg is None:
            raise ModuleNotFoundError("DearPyGui is required for DPG backend")
        assert dpg is not None
        InteractivePipeWindow.__init__(self, name=name, pipeline=pipeline, size=size)
        self.main_gui = main_gui
        assert self.pipeline is not None
        self.pipeline.global_params["__window"] = self

        # Determine viewport size
        viewport_width = 1200
        viewport_height = 800
        if size is not None:
            if isinstance(size, tuple) and len(size) == 2:
                viewport_width, viewport_height = size
            elif isinstance(size, int):
                viewport_width = size

        # Create viewport
        dpg.create_viewport(title=self.name or "Interactive Pipeline", width=viewport_width, height=viewport_height)

        # Create main window
        self.window_tag = "main_window"
        dpg.add_window(
            label=self.name or "Interactive Pipeline",
            tag=self.window_tag,
            no_close=True,
            no_collapse=True,
            no_move=True,
            no_resize=True,
            no_title_bar=True,
            no_scrollbar=True,
        )

        # Set as primary window
        dpg.set_primary_window(self.window_tag, True)

        # Create texture registry
        dpg.add_texture_registry(tag="texture_registry")

        # Create horizontal layout: controls on left, displays on right
        self.main_layout_tag = "main_layout"
        dpg.add_group(horizontal=True, parent=self.window_tag, tag=self.main_layout_tag)

        # Left panel for controls
        self.control_panel_width = 300
        self.control_panel_tag = "control_panel"
        dpg.add_child_window(
            width=self.control_panel_width,
            parent=self.main_layout_tag,
            tag=self.control_panel_tag,
            border=True,
        )

        # Right side for images/plots
        self.display_panel_tag = "display_panel"
        dpg.add_group(horizontal=False, parent=self.main_layout_tag, tag=self.display_panel_tag)

        # Image grid container (will hold images in grid)
        self.image_grid_tag = "image_grid"
        dpg.add_group(horizontal=False, parent=self.display_panel_tag, tag=self.image_grid_tag)

        # Initialize controls
        self.init_sliders(controls)

    def init_sliders(self, controls: List[Control]):
        """Initialize control widgets."""
        self.ctrl = {}
        self.widget_list = {}
        self.name_label = {}
        self.result_label = {}
        control_factory = ControlFactory()

        # Collect panels and ungrouped controls
        root_panels = set()
        ungrouped_controls = []

        for ctrl in controls:
            self.ctrl[ctrl.name] = ctrl
            if ctrl.panel is None:
                ungrouped_controls.append(ctrl)
            else:
                root_panel = ctrl.panel.get_root()
                root_panels.add(root_panel)

        # Filter out detached panels for now (not fully implemented)
        regular_panels = [p for p in root_panels if not p.detached]

        # Group panels by position
        panels_by_position = {"top": [], "left": [], "right": [], "bottom": []}
        for panel in regular_panels:
            pos = panel.position or "bottom"
            panels_by_position[pos].append(panel)

        # Render panels and controls to control panel
        # For simplicity, all controls go to the left control panel
        for panel in panels_by_position["bottom"]:  # Bottom panels go to control panel
            self._build_panel_widget(panel, control_factory, self.control_panel_tag)

        for ctrl in ungrouped_controls:
            self._create_control_widget(ctrl, control_factory, self.control_panel_tag)

    def _build_panel_widget(self, panel: Panel, control_factory: ControlFactory, parent):
        """Build DPG widget for a panel."""
        assert dpg is not None
        if panel.collapsible:
            # Use collapsing header
            header_tag = f"panel_{panel.name}_header"
            dpg.add_collapsing_header(
                label=panel.name or "",
                default_open=not panel.collapsed,
                parent=parent,
                tag=header_tag,
            )
            panel_parent = header_tag
        else:
            # Use regular group
            group_tag = f"panel_{panel.name}_group"
            dpg.add_group(parent=parent, tag=group_tag)
            if panel.name:
                dpg.add_text(panel.name, parent=group_tag, color=(255, 255, 0))
                dpg.add_separator(parent=group_tag)
            panel_parent = group_tag

        # Add child panels and controls
        if panel.elements:
            for element in panel.elements:
                if isinstance(element, Panel):
                    self._build_panel_widget(element, control_factory, panel_parent)
                elif isinstance(element, Control):
                    self._create_control_widget(element, control_factory, panel_parent)

        # Add controls assigned directly to panel
        for ctrl in panel._controls:
            self._create_control_widget(ctrl, control_factory, panel_parent)

    def _create_control_widget(self, ctrl: Control, control_factory: ControlFactory, parent):
        """Create a single control widget."""
        assert dpg is not None
        slider_name = ctrl.name

        if isinstance(ctrl, KeyboardControl):
            if self.main_gui is not None:
                self.main_gui.bind_keyboard_slider(ctrl, self.key_update_parameter)
            return None
        elif isinstance(ctrl, TimeControl):
            # Time control not fully implemented for DPG yet
            logging.warning("TimeControl not fully implemented for DPG backend")
            return None
        elif isinstance(ctrl, Control):
            slider_instance = control_factory.create_control(ctrl, self.update_parameter)
            if slider_instance is None:
                return None

            # Create label
            label_tag = f"{slider_name}_label"
            dpg.add_text(f"{ctrl.name}:", parent=parent, tag=label_tag)
            self.name_label[slider_name] = label_tag

            # Create control widget
            slider_widget = slider_instance.create(parent)
            self.widget_list[slider_name] = slider_instance

            # Create value display
            result_tag = f"{slider_name}_result"
            val = ctrl.value
            val_to_print = f"{val:.3e}" if isinstance(val, float) else str(val)
            dpg.add_text(f"{val_to_print}", parent=parent, tag=result_tag)
            self.result_label[slider_name] = result_tag

            dpg.add_spacer(height=5, parent=parent)

            return slider_widget
        return None

    def update_label(self, idx):
        """Update the label displaying the current value."""
        assert dpg is not None
        val = self.ctrl[idx].value
        val_to_print = f"{val:.3e}" if isinstance(val, float) else str(val)
        if idx in self.result_label:
            dpg.set_value(self.result_label[idx], f"{val_to_print}")

    def update_parameter(self, idx, value):
        """Called when a control value changes."""
        logging.debug(f"DPG update_parameter: idx={idx}, value={value}, type={type(value)}")
        if self.ctrl[idx]._type is str:
            if self.ctrl[idx].value_range is None:
                self.ctrl[idx].update(value)
            else:
                self.ctrl[idx].update(self.ctrl[idx].value_range[value])
        elif self.ctrl[idx]._type is bool:
            self.ctrl[idx].update(bool(value))
        elif self.ctrl[idx]._type is float:
            self.ctrl[idx].update(float(value))
        elif self.ctrl[idx]._type is int:
            self.ctrl[idx].update(int(value))
        else:
            raise NotImplementedError(f"{self.ctrl[idx]._type} not supported")
        self.update_label(idx)
        self.refresh()

    def key_update_parameter(self, idx, down):
        """Update parameter via keyboard."""
        if down:
            self.ctrl[idx].on_key_down()
        else:
            self.ctrl[idx].on_key_up()
        self.refresh()

    def check_image_canvas_changes(self, expected_image_canvas_shape):
        """Override to properly clean up DPG items when layout changes."""
        if self.image_canvas is not None:
            assert dpg is not None
            # Shallow copy so type is clearly a list (avoids Pyright "Never" in this block)
            canvas: List[Any] = list(self.image_canvas)
            current_canvas_shape = (
                len(canvas),
                max(len(image_row) for image_row in canvas),
            )
            if current_canvas_shape != expected_image_canvas_shape:
                # Delete all textures from texture registry first (iterate over copy)
                for row_content in canvas:
                    for img_widget in row_content:
                        if img_widget is not None and "texture" in img_widget:
                            texture_tag = img_widget["texture"]
                            if dpg.does_item_exist(texture_tag):
                                dpg.delete_item(texture_tag)
                            # Also remove alias if it exists
                            if dpg.does_alias_exist(texture_tag):
                                dpg.remove_alias(texture_tag)

                # Clear all children of image_grid (rows, cells, images, plots, etc.)
                if dpg.does_item_exist(self.image_grid_tag):
                    dpg.delete_item(self.image_grid_tag, children_only=True)

                self.image_canvas = None
                logging.info(
                    "DPG: Cleared image grid for layout change: %s -> %s",
                    current_canvas_shape,
                    expected_image_canvas_shape,
                )

    def add_image_placeholder(self, row, col):
        """Add placeholder for image at grid position."""
        assert dpg is not None
        assert self.image_canvas is not None
        # Create texture and image widget
        placeholder_tag = f"image_{row}_{col}"
        title_tag = f"title_{row}_{col}"

        # Create a vertical group for this cell
        cell_tag = f"cell_{row}_{col}"

        # Find or create row group
        row_tag = f"row_{row}"
        if not dpg.does_item_exist(row_tag):
            dpg.add_group(horizontal=True, parent=self.image_grid_tag, tag=row_tag)

        # Create cell group in row
        dpg.add_group(horizontal=False, parent=row_tag, tag=cell_tag)

        # Title
        dpg.add_text("", parent=cell_tag, tag=title_tag)

        # Placeholder image (1x1 pixel)
        placeholder_data = [1.0, 1.0, 1.0, 1.0]  # White pixel
        texture_tag = f"texture_{row}_{col}"
        dpg.add_dynamic_texture(
            width=1, height=1, default_value=placeholder_data, tag=texture_tag, parent="texture_registry"
        )

        dpg.add_image(texture_tag, parent=cell_tag, tag=placeholder_tag)

        self.image_canvas[row][col] = {
            "image": placeholder_tag,
            "title": title_tag,
            "texture": texture_tag,
            "cell_tag": cell_tag,
            "type": "image",
            "plot_object": None,
            "ax_placeholder": None,
        }

    def delete_image_placeholder(self, img_widget_dict):
        """Delete image placeholder and associated items."""
        assert dpg is not None
        # Delete texture (stored in texture registry, not parented to cell)
        if "texture" in img_widget_dict and dpg.does_item_exist(img_widget_dict["texture"]):
            dpg.delete_item(img_widget_dict["texture"])

        # Delete cell group (this recursively deletes title, image, plot, text, etc.)
        if "cell_tag" in img_widget_dict and dpg.does_item_exist(img_widget_dict["cell_tag"]):
            dpg.delete_item(img_widget_dict["cell_tag"])

    def update_image(self, content, row, col):
        """Update image/plot/table at grid position."""
        assert dpg is not None
        assert self.image_canvas is not None
        cell_dict = self.image_canvas[row][col]

        # Update title
        title_tag = cell_dict["title"]
        current_style = self.get_current_style(row, col)
        dpg.set_value(title_tag, current_style.get("title", ""))

        # Handle different content types
        if isinstance(content, np.ndarray):
            if len(content.shape) == 1:
                # 1D array - treat as curve
                if CURVE_SUPPORT and Curve is not None and SingleCurve is not None:
                    content = Curve(
                        cast(
                            List,
                            [SingleCurve(y=content)],
                        ),
                        ylabel="Amplitude",
                    )
                else:
                    logging.warning("1D array requires Curve support")
                    return
            else:
                # 2D/3D array - image
                self._update_image_texture(content, row, col)
                return

        if CURVE_SUPPORT and Curve is not None and isinstance(content, Curve):
            self._update_curve(content, row, col)
        elif CURVE_SUPPORT and Table is not None and isinstance(content, Table):
            logging.warning("Table display not fully implemented for DPG backend")
            self._update_text(str(content), row, col)
        elif isinstance(content, str):
            self._update_text(content, row, col)

    def _update_image_texture(self, img_array, row, col):
        """Update image texture with numpy array."""
        assert dpg is not None
        assert self.image_canvas is not None
        cell_dict = self.image_canvas[row][col]
        texture_tag = cell_dict["texture"]
        image_tag = cell_dict["image"]

        # Convert image to RGBA float32 format
        converted_img = self.convert_image_to_dpg(img_array)
        h, w = img_array.shape[:2]

        # Check if we need to recreate texture (size changed)
        if dpg.does_item_exist(texture_tag):
            # Get current texture size
            config = dpg.get_item_configuration(texture_tag)
            current_width = config.get("width", 0)
            current_height = config.get("height", 0)

            if current_width != w or current_height != h:
                logging.debug(f"DPG texture size changed: {current_width}x{current_height} -> {w}x{h}")
                # Size changed - need to recreate both texture and image widget

                # Delete old texture and image widget
                dpg.delete_item(texture_tag)
                if dpg.does_alias_exist(texture_tag):
                    dpg.remove_alias(texture_tag)
                if dpg.does_item_exist(image_tag):
                    dpg.delete_item(image_tag)

                # Create new texture with same tag
                dpg.add_dynamic_texture(
                    width=w, height=h, default_value=converted_img, tag=texture_tag, parent="texture_registry"
                )

                # Recreate image widget with same tag
                cell_tag = cell_dict["cell_tag"]
                dpg.add_image(texture_tag, parent=cell_tag, tag=image_tag)
            else:
                # Same size - just update data
                dpg.set_value(texture_tag, converted_img)
        else:
            # Texture doesn't exist - create it
            dpg.add_dynamic_texture(
                width=w, height=h, default_value=converted_img, tag=texture_tag, parent="texture_registry"
            )

    def _update_curve(self, curve, row, col):
        """Update curve plot using DPG native plotting."""
        assert dpg is not None
        canvas = self.image_canvas
        if canvas is None:
            return
        cell_dict = canvas[row][col]

        # Check if plot already exists
        plot_tag = f"plot_{row}_{col}"
        x_axis_tag = f"x_axis_{row}_{col}"
        y_axis_tag = f"y_axis_{row}_{col}"

        if not dpg.does_item_exist(plot_tag):
            # Create new plot
            cell_tag = f"cell_{row}_{col}"

            # Remove old image if present
            if dpg.does_item_exist(cell_dict["image"]):
                dpg.delete_item(cell_dict["image"])

            # Create plot
            dpg.add_plot(label="", height=400, width=500, no_title=True, parent=cell_tag, tag=plot_tag, no_menus=True)

            dpg.add_plot_legend(parent=plot_tag)
            dpg.add_plot_axis(
                dpg.mvXAxis, label=curve.xlabel if hasattr(curve, "xlabel") else "", parent=plot_tag, tag=x_axis_tag
            )
            dpg.add_plot_axis(
                dpg.mvYAxis, label=curve.ylabel if hasattr(curve, "ylabel") else "", parent=plot_tag, tag=y_axis_tag
            )

            cell_dict["plot_object"] = plot_tag
            cell_dict["type"] = "plot"

        # Update or create series
        for idx, single_curve in enumerate(curve.curves):
            series_tag = f"series_{row}_{col}_{idx}"

            x_raw = single_curve.x if single_curve.x is not None else list(range(len(single_curve.y)))
            if isinstance(x_raw, np.ndarray):
                x_data = [float(x) for x in cast(np.ndarray, x_raw).tolist()]
            else:
                x_data = [float(x) for x in list(x_raw)]
            if isinstance(single_curve.y, np.ndarray):
                y_raw = single_curve.y.tolist()
            else:
                y_raw = list(single_curve.y)
            y_data = [float(y) for y in y_raw]

            if dpg.does_item_exist(series_tag):
                # Update existing series
                dpg.set_value(series_tag, [x_data, y_data])
            else:
                # Create new series
                label = single_curve.label if hasattr(single_curve, "label") and single_curve.label else f"Series {idx}"
                dpg.add_line_series(x_data, y_data, label=label, parent=y_axis_tag, tag=series_tag)

    def _update_text(self, text, row, col):
        """Update text display."""
        assert dpg is not None
        canvas = self.image_canvas
        if canvas is None:
            return
        cell_dict = canvas[row][col]
        text_tag = f"text_{row}_{col}"

        if dpg.does_item_exist(text_tag):
            dpg.set_value(text_tag, text)
        else:
            # Create text widget
            cell_tag = f"cell_{row}_{col}"
            if dpg.does_item_exist(cell_dict["image"]):
                dpg.delete_item(cell_dict["image"])
            dpg.add_text(text, parent=cell_tag, tag=text_tag, wrap=400)
            cell_dict["image"] = text_tag

    @staticmethod
    def convert_image_to_dpg(img):
        """Convert numpy image to DPG texture format (RGBA float32 flattened)."""
        if not isinstance(img, np.ndarray):
            return img

        # Clip to 0-1 range
        img = img.clip(0.0, 1.0).astype(np.float32)

        # Convert to RGBA
        if img.ndim == 2:
            # Grayscale -> RGBA
            img = np.stack([img, img, img, np.ones_like(img)], axis=-1)
        elif img.shape[-1] == 3:
            # RGB -> RGBA
            alpha = np.ones((*img.shape[:-1], 1), dtype=np.float32)
            img = np.concatenate([img, alpha], axis=-1)
        elif img.shape[-1] == 4:
            # Already RGBA
            pass
        else:
            raise ValueError(f"Unsupported image shape: {img.shape}")

        # Flatten for DPG
        return img.flatten().tolist()

    @staticmethod
    def convert_image(out_im):
        """Convert image for display (keep in 0-1 range for DPG)."""
        if isinstance(out_im, np.ndarray) and len(out_im.shape) > 1:
            return out_im.clip(0.0, 1.0).astype(np.float32)
        else:
            return out_im

    def refresh(self):
        """Refresh display by running pipeline."""
        if self.pipeline is not None:
            out = self.pipeline.run()
            self.refresh_display(out)

    def reset_sliders(self):
        """Reset all sliders to default values."""
        for widget_idx, ctrl in self.ctrl.items():
            if widget_idx in self.widget_list:
                self.widget_list[widget_idx].reset()
            self.update_label(widget_idx)
        self.refresh()
