"""Dear PyGui backend (``gui="dpg"``).

A single Dear PyGui viewport hosts one primary window laid out as
``top panels | (left panels | image grid | right panels) | bottom controls``;
detached panels float in their own windows. Images are uploaded as raw float
textures, curves and tables use the native plot and table widgets.

Keyboard shortcuts come from a global key-press handler (muted while a text
entry has focus), ``TimeControl`` timers are ticked from the render loop.

Construction (``InteractivePipeDPG(...)``) only needs a Dear PyGui context and
works without a display; the viewport is created in ``run()``.
"""

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from interactive_pipe.data_objects.curves import Curve
from interactive_pipe.data_objects.table import Table
from interactive_pipe.graphical.dpg_backend import (  # noqa: F401
    INSTALL_HINT,
    context_alive,
    create_context,
    destroy_context,
    dpg,
    key_code_table,
)
from interactive_pipe.graphical.dpg_control import ControlFactory
from interactive_pipe.graphical.dpg_image import (
    clear_cell_content,
    signal_to_curve,
    update_curve_cell,
    update_image_cell,
    update_table_cell,
    update_text_cell,
)
from interactive_pipe.graphical.dpg_panels import DpgPanelBuilder, DpgTimer  # noqa: F401
from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.graphical.window import InteractivePipeWindow, display_kind
from interactive_pipe.headless.control import Control, TimeControl
from interactive_pipe.headless.pipeline import HeadlessPipeline

DEFAULT_VIEWPORT_SIZE = (1280, 800)
GRID_SPACING = 6  # pixels between cells
TITLE_HEIGHT = 22  # one text line above each cell
LAYOUT_MARGIN = 16  # window padding
SIDE_PANEL_GAP = 8
SIDE_PANEL_WIDTH = 320  # left/right panel columns


class InteractivePipeDPG(InteractivePipeGUI):
    """Interactive pipeline GUI based on Dear PyGui."""

    def init_app(self, **kwargs):
        create_context()
        self.window = MainWindow(
            controls=self.controls,
            name=self.name,
            pipeline=self.pipeline,
            size=self.size,
            main_gui=self,
            **kwargs,
        )
        self.set_default_key_bindings()
        self._key_codes = key_code_table()
        dpg.add_key_press_handler(callback=self._on_key_press, parent=dpg.add_handler_registry())
        self.full_screen_toggle = False
        self._viewport_shown = False
        if self.audio:
            logging.warning("Audio playback is not supported by the dpg backend (use gui='qt' or gui='gradio').")

    # ----------------------------------------------------------------- running
    def run(self) -> list:
        if not self.pipeline._PipelineCore__initialized_inputs:  # type: ignore[attr-defined]
            raise RuntimeError("Did you forget to initialize the pipeline inputs?")
        width, height = self.window.viewport_size
        dpg.create_viewport(title=self.name or "interactive_pipe", width=width, height=height)
        dpg.set_viewport_resize_callback(self.window.on_viewport_resize)
        dpg.setup_dearpygui()
        requested = self.window.window_size
        maximized = isinstance(requested, str) and "max" in requested.lower()
        dpg.show_viewport(maximized=maximized)
        self._viewport_shown = True
        if isinstance(requested, str) and "full" in requested.lower():
            self.full_screen_toggle = True
            dpg.toggle_viewport_fullscreen()
        self.window.viewport_ready = True
        self.window.refresh()
        # sizes measured on the first frame drive the layout of the second one
        dpg.set_frame_callback(2, lambda *_args: self.window.relayout())
        while dpg.is_dearpygui_running():
            self.window.tick_timers()
            dpg.render_dearpygui_frame()
        destroy_context()
        self.custom_end()
        results = self.pipeline.results
        if results is None:
            return []
        if isinstance(results, tuple):
            return list(results)
        return results  # type: ignore[return-value]

    def close(self):
        """close GUI"""
        if self._viewport_shown:
            dpg.stop_dearpygui()
        elif context_alive():
            destroy_context()

    def _on_key_press(self, _sender, key_code, _user_data):
        if self.window.text_entry_focused():
            return  # typing in a prompt: never trigger shortcuts
        key = self._key_codes.get(key_code)
        if key is None:
            return
        self.on_press(key, refresh_func=self.window.refresh)

    # ------------------------------------------------------------- key actions
    def reset_parameters(self):
        """reset sliders to default parameters"""
        super().reset_parameters()
        for ctrl in self.window.ctrl.values():
            if isinstance(ctrl, TimeControl):
                self.start_time = None  # Reset the timer
            ctrl.value = ctrl.value_default
        self.window.reset_sliders()

    def on_parameters_loaded(self):
        """sync the widgets with the imported parameters"""
        # HeadlessPipeline.parameters (set by import_tuning) writes the loaded
        # values back into the connected controls; the widgets just need syncing.
        self.window.reset_sliders()

    def toggle_full_screen(self):
        """toggle full screen"""
        self.full_screen_toggle = not self.full_screen_toggle
        if self._viewport_shown:
            dpg.toggle_viewport_fullscreen()

    def print_message(self, message_list: List[str]):
        print("\n".join(message_list))
        self.window.show_message(self.name or "interactive_pipe", message_list)


class MainWindow(InteractivePipeWindow):
    """Primary Dear PyGui window: panels around a centered, uniformly scaled image grid."""

    def __init__(
        self,
        *args,
        controls=None,
        name="",
        pipeline: Optional[HeadlessPipeline] = None,
        size=None,
        main_gui=None,
        **kwargs,
    ):
        if controls is None:
            controls = []
        InteractivePipeWindow.__init__(self, name=name, pipeline=pipeline, size=size, **kwargs)
        self.main_gui = main_gui
        self.viewport_ready = False
        self._viewport_client: Optional[Tuple[int, int]] = None
        self.detached_windows: List[Any] = []
        self.timers: List[DpgTimer] = []
        self.timer: Optional[DpgTimer] = None
        self.prompt_widgets: List[Any] = []
        self.sized_items: List[Tuple[Any, Callable[[], int]]] = []  # (item, width_fn) re-applied on relayout
        self._message_window: Optional[Any] = None
        self._rows: Dict[int, Dict[str, Any]] = {}
        self._needs_layout = False
        self.scale_factor = 1.0

        self.texture_registry = dpg.add_texture_registry()
        self.root = dpg.add_window(
            label=self.name or "interactive_pipe",
            no_title_bar=True,
            no_move=True,
            no_resize=True,
            no_collapse=True,
            no_close=True,
            no_scrollbar=False,
        )
        dpg.set_primary_window(self.root, True)
        self.top_container = dpg.add_group(parent=self.root)
        self.middle_container = dpg.add_group(parent=self.root, horizontal=True, horizontal_spacing=SIDE_PANEL_GAP)
        # side containers are created by init_sliders only when a panel sits there
        self.left_container: Optional[Any] = None
        self.right_container: Optional[Any] = None
        self.grid_container = dpg.add_child_window(parent=self.middle_container, border=False, no_scrollbar=True)
        self.grid_vspacer = dpg.add_spacer(parent=self.grid_container, height=0)
        self.image_grid = dpg.add_group(parent=self.grid_container)
        self.bottom_container = dpg.add_group(parent=self.root)
        self.window_size = size  # validated by the setter
        self.init_sliders(controls)

    # ---------------------------------------------------------------- sizing
    @property
    def window_size(self):
        return self._size

    @window_size.setter
    def window_size(self, _size):
        if isinstance(_size, str) and "full" not in _size.lower() and "max" not in _size.lower():
            raise ValueError(f"size={_size} can only be among (full, fullscreen, maximized, max, maximum)")
        self._size = _size

    @property
    def viewport_size(self) -> Tuple[int, int]:
        """Initial viewport size derived from the requested window size."""
        requested = self.window_size
        if isinstance(requested, int):
            return requested, int(requested * 0.75)
        if isinstance(requested, (tuple, list)) and len(requested) == 2:
            return int(requested[0]), int(requested[1])
        return DEFAULT_VIEWPORT_SIZE

    def _client_size(self) -> Tuple[int, int]:
        if self._viewport_client is not None:
            return self._client_size_or_default(self._viewport_client)
        if self.viewport_ready:
            return self._client_size_or_default((dpg.get_viewport_client_width(), dpg.get_viewport_client_height()))
        return self.viewport_size

    def _client_size_or_default(self, size: Tuple[int, int]) -> Tuple[int, int]:
        width, height = size
        return (width, height) if width > 0 and height > 0 else self.viewport_size

    def on_viewport_resize(self, _sender, app_data):
        """Viewport resize callback: app_data = [width, height, client_width, client_height]."""
        if app_data and len(app_data) >= 4:
            self._viewport_client = (int(app_data[2]), int(app_data[3]))
        self.relayout()

    @staticmethod
    def _measured_height(item) -> int:
        """Rendered height of a container (0 before the first frame or when it has no children)."""
        if not dpg.get_item_children(item, 1):
            return 0
        size = dpg.get_item_rect_size(item)
        return int(size[1]) if size and len(size) >= 2 else 0

    def natural_grid_size(self) -> Tuple[List[int], List[int]]:
        """Per-column widths and per-row heights of the canvas at native size (titles included)."""
        if not self.image_canvas:
            return [], []
        ncols = max(len(row) for row in self.image_canvas)
        col_widths = [0] * ncols
        row_heights = [0] * len(self.image_canvas)
        for r, row in enumerate(self.image_canvas):
            for c, cell in enumerate(row):
                if cell is None or cell.get("natural_size") is None:
                    continue
                width, height = cell["natural_size"]
                col_widths[c] = max(col_widths[c], int(width))
                row_heights[r] = max(row_heights[r], int(height) + TITLE_HEIGHT)
        return col_widths, row_heights

    def relayout(self):
        """Fit the image grid in the space left by the panels (uniform scale, centered)."""
        self._needs_layout = False
        if not self.image_canvas:
            return
        client_w, client_h = self._client_size()
        side_containers = [item for item in (self.left_container, self.right_container) if item is not None]
        avail_w = max(100, client_w - len(side_containers) * (SIDE_PANEL_WIDTH + SIDE_PANEL_GAP) - LAYOUT_MARGIN)
        top_h = self._measured_height(self.top_container)
        bottom_h = self._measured_height(self.bottom_container)
        avail_h = max(80, client_h - top_h - bottom_h - LAYOUT_MARGIN - 2 * GRID_SPACING)
        dpg.configure_item(self.grid_container, width=avail_w, height=avail_h)
        for item in side_containers:
            dpg.configure_item(item, height=avail_h)
        for item, width_fn in self.sized_items:
            if dpg.does_item_exist(item):
                dpg.configure_item(item, width=width_fn())

        col_widths, row_heights = self.natural_grid_size()
        total_w = sum(col_widths) + GRID_SPACING * max(0, len(col_widths) - 1)
        total_h = sum(row_heights) + GRID_SPACING * max(0, len(row_heights) - 1)
        if total_w <= 0 or total_h <= 0:
            return
        scale = min(avail_w / total_w, (avail_h - LAYOUT_MARGIN) / total_h)
        self.scale_factor = scale
        for r, row in enumerate(self.image_canvas):
            for cell in row:
                if cell is None or cell.get("natural_size") is None or cell.get("content") is None:
                    continue
                width, height = cell["natural_size"]
                kind = cell.get("kind")
                if kind == "text":
                    dpg.configure_item(cell["content"], wrap=max(40, int(width * scale)))
                else:
                    dpg.configure_item(
                        cell["content"], width=max(1, int(width * scale)), height=max(1, int(height * scale))
                    )
            row_items = self._rows.get(r)
            if row_items is not None:
                row_w = sum(int(w * scale) for w in col_widths[: len(row)]) + GRID_SPACING * max(0, len(row) - 1)
                dpg.configure_item(row_items["spacer"], width=max(0, (avail_w - row_w) // 2))
        dpg.configure_item(self.grid_vspacer, height=max(0, (avail_h - int(total_h * scale) - LAYOUT_MARGIN) // 2))

    # --------------------------------------------------------------- controls
    def init_sliders(self, controls: List[Control]):
        self.ctrl = {}
        self.widget_list = {}
        self.name_label = {}
        self.result_label = {}
        control_factory = ControlFactory(texture_registry=self.texture_registry)
        builder = DpgPanelBuilder(self, control_factory)

        root_panels = []
        ungrouped_controls = []
        for ctrl in controls:
            self.ctrl[ctrl.name] = ctrl
            if ctrl.panel is None:
                ungrouped_controls.append(ctrl)
            else:
                root_panel = ctrl.panel.get_root()
                if root_panel not in root_panels:
                    root_panels.append(root_panel)
        panels_by_position = {"top": [], "left": [], "right": [], "bottom": []}
        detached_panels = []
        for panel in root_panels:
            if panel.detached:
                detached_panels.append(panel)
            else:
                panels_by_position[panel.position or "bottom"].append(panel)

        def full_width() -> int:
            return self._client_size()[0] - LAYOUT_MARGIN

        def side_width() -> int:
            return SIDE_PANEL_WIDTH

        if panels_by_position["left"]:
            self.left_container = dpg.add_child_window(
                parent=self.middle_container, before=self.grid_container, width=SIDE_PANEL_WIDTH, border=False
            )
        if panels_by_position["right"]:
            self.right_container = dpg.add_child_window(
                parent=self.middle_container, width=SIDE_PANEL_WIDTH, border=False
            )
        for panel in panels_by_position["top"]:
            builder.build_panel(panel, self.top_container, full_width)
        for panel in panels_by_position["left"]:
            builder.build_panel(panel, self.left_container, side_width)
        for panel in panels_by_position["right"]:
            builder.build_panel(panel, self.right_container, side_width)
        for ctrl in ungrouped_controls:
            builder.create_control_row(ctrl, self.bottom_container)
        for panel in panels_by_position["bottom"]:
            builder.build_panel(panel, self.bottom_container, full_width)
        for panel in detached_panels:
            builder.build_detached_window(panel)

    def on_detached_closed(self, sender, *_args):
        if sender in self.detached_windows:
            self.detached_windows.remove(sender)

    def text_entry_focused(self) -> bool:
        return any(dpg.does_item_exist(item) and dpg.is_item_focused(item) for item in self.prompt_widgets)

    def tick_timers(self):
        now = time.time()
        for timer in self.timers:
            timer.tick(now)

    def update_label(self, idx):
        if idx in self.name_label:
            dpg.set_value(self.name_label[idx], f"{self.ctrl[idx].name}")

    def update_parameter(self, idx, value):
        """Apply a new value (expressed in the control's own domain) and refresh."""
        self.ctrl[idx].update(value)
        self.update_label(idx)
        self.refresh()

    def key_update_parameter(self, idx, down):
        """Required implementation for keyboard sliders update"""
        if down:
            self.ctrl[idx].on_key_down()
        else:
            self.ctrl[idx].on_key_up()
        if idx in self.widget_list:
            self.widget_list[idx].reset()
        self.refresh()

    def reset_sliders(self):
        for widget_idx in self.ctrl:
            if widget_idx in self.widget_list:
                self.widget_list[widget_idx].reset()
            self.update_label(widget_idx)
        self.refresh()

    # ----------------------------------------------------------------- canvas
    def check_image_canvas_changes(self, expected_image_canvas_shape):
        super().check_image_canvas_changes(expected_image_canvas_shape)
        if self.image_canvas is None:
            for row_items in self._rows.values():
                for item in (row_items["group"], row_items["gap"]):
                    if dpg.does_item_exist(item):
                        dpg.delete_item(item)
            self._rows = {}
            self._needs_layout = True

    def _row_group(self, row: int):
        row_items = self._rows.get(row)
        if row_items is None:
            group = dpg.add_group(parent=self.image_grid, horizontal=True, horizontal_spacing=GRID_SPACING)
            spacer = dpg.add_spacer(parent=group, width=0)
            gap = dpg.add_spacer(parent=self.image_grid, height=GRID_SPACING)
            row_items = {"group": group, "spacer": spacer, "gap": gap}
            self._rows[row] = row_items
        return row_items["group"]

    def add_image_placeholder(self, row, col):
        cell_group = dpg.add_group(parent=self._row_group(row))
        title = dpg.add_text("", parent=cell_group)
        self.image_canvas[row][col] = {  # type: ignore[index]
            "cell": cell_group,
            "title": title,
            "content": None,
            "texture": None,
            "buffer": None,
            "plot": None,
            "kind": None,
            "natural_size": None,
        }
        self._needs_layout = True

    def delete_image_placeholder(self, cell):
        clear_cell_content(cell)
        if dpg.does_item_exist(cell["cell"]):
            dpg.delete_item(cell["cell"])

    def update_image(self, content, row, col):
        cell = self.image_canvas[row][col]  # type: ignore[index]
        if isinstance(content, np.ndarray) and content.ndim == 1:
            content = signal_to_curve(content)
        kind = display_kind(content)
        if cell.get("kind") not in (None, kind):
            clear_cell_content(cell)
        if isinstance(content, np.ndarray):
            changed = update_image_cell(cell, content, self.texture_registry)
        elif isinstance(content, Curve):
            changed = update_curve_cell(cell, content)
        elif isinstance(content, Table):
            changed = update_table_cell(cell, content)
        elif isinstance(content, str):
            changed = update_text_cell(cell, content)
        else:
            logging.warning(f"Unsupported output type for display: {type(content)}")
            changed = False
        cell["kind"] = kind
        self._needs_layout = self._needs_layout or changed
        dpg.set_value(cell["title"], self.get_current_style(row, col).get("title", ""))

    @staticmethod
    def convert_image(out_im):
        if isinstance(out_im, np.ndarray) and out_im.ndim > 1:
            return out_im.clip(0.0, 1.0).astype(np.float32, copy=False)
        return out_im

    def refresh(self):
        if self.pipeline is not None:
            out = self.pipeline.run()
            self.refresh_display(out)
        if self._needs_layout:
            self.relayout()

    # --------------------------------------------------------------- messages
    def show_message(self, title: str, message_list: List[str]):
        """Modal window listing the message lines (help, graph errors)."""
        if self._message_window is not None and dpg.does_item_exist(self._message_window):
            dpg.delete_item(self._message_window)
        client_w, client_h = self._client_size()
        message_window = dpg.add_window(
            label=title, modal=True, autosize=True, no_saved_settings=True, pos=(client_w // 4, client_h // 4)
        )
        self._message_window = message_window
        for line in message_list:
            dpg.add_text(line, parent=message_window)
        dpg.add_button(
            label="Close",
            parent=message_window,
            callback=lambda *_args: dpg.configure_item(message_window, show=False),
        )
