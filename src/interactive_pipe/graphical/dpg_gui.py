"""Dear PyGui backend (``gui="dpg"``).

A single Dear PyGui viewport hosts one primary window laid out as
``top panels | (left panels | image grid | right panels) | bottom controls``;
detached panels float in their own windows. Images are uploaded as raw float
textures, curves and tables use the native plot and table widgets.

Keyboard shortcuts come from a global key-press handler (muted while a text
entry has focus), ``TimeControl`` timers are ticked from the render loop.
Image cells share one zoom/pan state (as on Qt): wheel zoom around the cursor,
left-drag pan, double-click fit, keys 0 (fit) / 1 (1:1) / + / -.

Construction (``InteractivePipeDPG(...)``) only needs a Dear PyGui context and
works without a display; the viewport is created in ``run()``.
"""

import logging
import math
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from interactive_pipe.core.engine import FilterError
from interactive_pipe.data_objects.curves import Curve
from interactive_pipe.data_objects.table import Table
from interactive_pipe.graphical.actions import Action
from interactive_pipe.graphical.columns import choose_column_count, columns_height, split_into_columns
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
    image_box,
    place_image,
    set_cell_title,
    signal_to_curve,
    update_curve_cell,
    update_image_cell,
    update_table_cell,
    update_text_cell,
)
from interactive_pipe.graphical.dpg_panels import DpgPanelBuilder, DpgTimer  # noqa: F401
from interactive_pipe.graphical.dpg_viewer import ZOOM_STEP, ViewState
from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.graphical.window import (
    InteractivePipeWindow,
    display_kind,
    format_error_message,
    format_run_status,
)
from interactive_pipe.headless.control import Control, TimeControl
from interactive_pipe.headless.pipeline import HeadlessPipeline

DEFAULT_VIEWPORT_SIZE = (1280, 800)
GRID_SPACING = 6  # pixels between cells
TITLE_HEIGHT = 22  # one text line above each cell
LAYOUT_MARGIN = 16  # window padding
SIDE_PANEL_GAP = 8
SIDE_PANEL_WIDTH = 320  # left/right panel columns
MENU_BAR_HEIGHT = 22  # primary window menu bar
STATUS_BAR_HEIGHT = 20  # status line at the bottom of the primary window
STATUS_COLOR = (150, 150, 150, 255)
ERROR_COLOR = (230, 80, 80, 255)
FILE_DIALOG_SIZE = (640, 400)
SCROLLBAR_SIZE = 14  # ImGui default style
MIN_GRID_HEIGHT = 80  # the images keep at least this height (fit view)
MIN_BOTTOM_HEIGHT = 60  # the scrolling controls area keeps at least this height
LAYOUT_SETTLE_FRAMES = 2  # a relayout shows up in the measured item states after this many frames
MIN_CONTROL_COLUMN_WIDTH = 420  # the controls spread over columns at least this wide
CONTROL_COLUMN_GAP = 16  # pixels between the columns of controls
FIT_PREFERRED_HEIGHT = 600  # fit view: room the images get before the controls spread over columns
GRID_SLACK = (2 * 8 + GRID_SPACING, 2 * 8)  # 1:1 grid size beyond its cells: child window padding, row spacer


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
        self.window.add_menu_bar(self.actions_by_menu(), self._on_menu_item)
        self._key_codes = key_code_table()
        handler_registry = dpg.add_handler_registry()
        dpg.add_key_press_handler(callback=self._on_key_press, parent=handler_registry)
        self.window.add_mouse_handlers(handler_registry)
        self.full_screen_toggle = False
        self._viewport_shown = False
        if self.audio:
            logging.warning("Audio playback is not supported by the dpg backend (use gui='qt' or gui='gradio').")

    # ----------------------------------------------------------------- running
    def run(self) -> list:
        if not self.pipeline._PipelineCore__initialized_inputs:  # type: ignore[attr-defined]
            raise RuntimeError("Did you forget to initialize the pipeline inputs?")
        width, height = self.window.viewport_size
        try:
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
        finally:
            # always release the context and viewport, even when a filter raised from a timer tick,
            # so that a later run() can create a new viewport
            destroy_context()
            self._viewport_shown = False
            self.window.viewport_ready = False
        self.custom_end()
        results = self.pipeline.results
        if results is None:
            return []
        if isinstance(results, tuple):
            return list(results)
        return results  # type: ignore[return-value]

    def close(self):
        """close GUI"""
        if not context_alive():
            return  # already torn down (e.g. close() called again after run() returned)
        if self._viewport_shown:
            dpg.stop_dearpygui()
        else:
            destroy_context()

    def _on_key_press(self, _sender, key_code, _user_data):
        if self.window.text_entry_focused() or self.window.modal_shown():
            # typing in a prompt or in the file dialog's filename field: never trigger shortcuts
            return
        key = self._key_codes.get(key_code)
        if key is None:
            return
        self.on_press(key, refresh_func=self.window.refresh)

    def _on_menu_item(self, _sender, _app_data, action: Action):
        self.run_action(action)

    def _with_path(
        self,
        title: str,
        save: bool,
        extensions: List[str],
        default_name: str,
        on_path: Callable[[Path], None],
    ):
        """Native Dear PyGui file dialog once the viewport is shown, terminal before.

        The dialog is asynchronous: `on_path` runs from its callback.
        """
        if not self._viewport_shown:
            return super()._with_path(title, save, extensions, default_name, on_path)
        self.window.open_file_dialog(title, save, extensions, default_name, on_path)

    # ------------------------------------------------------------- key actions
    def reset_parameters(self):
        """reset sliders to default parameters and fit the images back to their cells"""
        super().reset_parameters()
        self.fit_view()
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
        if self._viewport_shown and context_alive():
            dpg.toggle_viewport_fullscreen()

    # ---------------------------------------------------- VIEW (image viewer)
    def fit_view(self):
        """fit the images to their cells"""
        self.window.set_view_mode("fit")

    def actual_size_view(self):
        """show the images at their actual size (1:1)"""
        self.window.set_view_mode("1:1")

    def zoom_in(self):
        """zoom in (all image cells)"""
        self.window.zoom_by(ZOOM_STEP)

    def zoom_out(self):
        """zoom out (all image cells)"""
        self.window.zoom_by(1.0 / ZOOM_STEP)

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
        self.menu_bar: Optional[Any] = None
        self.menu_items: Dict[str, Any] = {}
        self._file_dialog: Optional[Any] = None
        self._rows: Dict[int, Dict[str, Any]] = {}
        self._needs_layout = False
        self._refresh_pending = False  # set by update_parameter, flushed once per frame
        self.last_error: Optional[FilterError] = None
        self.scale_factor = 1.0
        self.view = ViewState()  # zoom/pan shared by every image cell
        self._size_before_actual: Optional[Tuple[int, int]] = None  # viewport size restored when leaving 1:1
        self._grow_request: Optional[Tuple[int, int]] = None  # last viewport size asked by a 1:1 growth
        self._grid_slack = list(GRID_SLACK)  # 1:1 grid size beyond its cells (paddings), learnt from overflow
        self._decoration = (0, 0)  # viewport outer size - client size
        self._frames_to_settle = 0  # frames before the grid overflow reflects the last relayout
        self._in_relayout = False
        self._drag: Optional[Tuple[Dict[str, Any], Tuple[float, float]]] = None  # (cell, last mouse pos)

        self.texture_registry = dpg.add_texture_registry()
        self.root = dpg.add_window(
            label=self.name or "interactive_pipe",
            no_title_bar=True,
            no_move=True,
            no_resize=True,
            no_collapse=True,
            no_close=True,
        )
        dpg.set_primary_window(self.root, True)
        # the window never scrolls: the images keep their place, the controls area scrolls
        # (set after set_primary_window, which resets these flags)
        dpg.configure_item(self.root, no_scrollbar=True, no_scroll_with_mouse=True)
        self.top_container = dpg.add_group(parent=self.root)
        self.middle_container = dpg.add_group(parent=self.root, horizontal=True, horizontal_spacing=SIDE_PANEL_GAP)
        # side containers are created by init_sliders only when a panel sits there
        self.left_container: Optional[Any] = None
        self.right_container: Optional[Any] = None
        # the grid never scrolls: it is sized to its cells (and the wheel zooms the images)
        self.grid_container = dpg.add_child_window(
            parent=self.middle_container, border=False, no_scrollbar=True, no_scroll_with_mouse=True
        )
        self.grid_vspacer = dpg.add_spacer(parent=self.grid_container, height=0)
        self.image_grid = dpg.add_group(parent=self.grid_container)
        # bottom controls: a group (measured at its natural height) in a child window that
        # scrolls when the controls do not fit under the images
        self.bottom_scroll = dpg.add_child_window(parent=self.root, border=False, height=-STATUS_BAR_HEIGHT)
        self.bottom_container = dpg.add_group(parent=self.bottom_scroll)
        self._bottom_scrolls = False
        # the controls below spread over columns when the images take the room
        self._bottom_items: List[Tuple[str, Any]] = []  # ("row" | "panel", item) in display order
        self._bottom_table: Optional[Any] = None  # table of the ungrouped controls (single column)
        self._columns_group: Optional[Any] = None  # horizontal group of column windows (2+ columns)
        self._control_columns = 1
        self._item_heights: Optional[List[int]] = None  # measured in a single column
        self._columns_settle = 0  # frames before the measured positions reflect the columns
        # status line: last run timings / errors
        self.status_text = dpg.add_text("", parent=self.root, color=STATUS_COLOR)
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
            # consistent outer/client pair: title bar and borders around the client area
            self._decoration = (
                max(0, int(app_data[0]) - int(app_data[2])),
                max(0, int(app_data[1]) - int(app_data[3])),
            )
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
        """Fit the image grid in the space left by the panels (uniform scale, centered).

        In the 1:1 view family the cells take their native size instead and the
        grid grows or shrinks to them, pushing the panels around (the viewport
        grows to fit them, within what the window manager grants).
        """
        if self._in_relayout:
            self._needs_layout = True  # e.g. a viewport resize callback fired by the growth below
            return
        self._in_relayout = True
        try:
            self._relayout()
        finally:
            self._in_relayout = False
        if self._needs_layout:
            self.relayout()

    def _relayout(self):
        self._needs_layout = False
        self._frames_to_settle = LAYOUT_SETTLE_FRAMES
        if not self.image_canvas:
            return
        client_w, client_h = self._client_size()
        side_containers = [item for item in (self.left_container, self.right_container) if item is not None]
        avail_w = max(100, client_w - len(side_containers) * (SIDE_PANEL_WIDTH + SIDE_PANEL_GAP) - LAYOUT_MARGIN)
        top_h = self._measured_height(self.top_container)
        menu_h = MENU_BAR_HEIGHT if self.menu_bar is not None else 0
        fixed_h = menu_h + STATUS_BAR_HEIGHT + top_h + LAYOUT_MARGIN + 2 * GRID_SPACING
        bottom_h = self._layout_control_columns(client_w, client_h - fixed_h - self._images_preferred_height(avail_w))
        # the controls get their natural height unless that leaves the images less than
        # MIN_GRID_HEIGHT: then they scroll in their own area
        bottom_shown = min(bottom_h, max(MIN_BOTTOM_HEIGHT, client_h - fixed_h - MIN_GRID_HEIGHT))
        avail_h = max(MIN_GRID_HEIGHT, client_h - fixed_h - bottom_shown)
        col_widths, row_heights = self.natural_grid_size()
        total_w = sum(col_widths) + GRID_SPACING * max(0, len(col_widths) - 1)
        total_h = sum(row_heights) + GRID_SPACING * max(0, len(row_heights) - 1)
        if self.view.absolute and total_w > 0 and total_h > 0:
            # 1:1 family: cells at native size, the grid takes exactly the room they need
            # and the viewport grows to show it whole. When the window manager does not grant
            # that size (screen limit), the images still show whole and the panels below
            # overflow the viewport (the primary window scrolls to reach them).
            slack_w, slack_h = self._grid_slack[0], LAYOUT_MARGIN + self._grid_slack[1]
            self._grow_viewport(
                client_w + max(0, total_w + slack_w - avail_w),
                max(client_h, fixed_h + bottom_h + total_h + slack_h),
            )
            avail_w = max(avail_w, total_w + slack_w)
            avail_h = total_h + slack_h
            # images first: the controls take the room left (when the screen caps the
            # window growth) and scroll in their own area
            bottom_shown = min(bottom_h, max(MIN_BOTTOM_HEIGHT, client_h - fixed_h - avail_h))
        dpg.configure_item(self.grid_container, width=avail_w, height=avail_h)
        if bottom_h > 0:
            dpg.configure_item(self.bottom_scroll, height=bottom_shown)
        self._bottom_scrolls = bottom_shown < bottom_h
        for item in side_containers:
            dpg.configure_item(item, height=avail_h)
        for item, width_fn in self.sized_items:
            if dpg.does_item_exist(item):
                dpg.configure_item(item, width=width_fn())
        if total_w <= 0 or total_h <= 0:
            return
        if self.view.absolute:
            scale = scale_h = 1.0
        else:
            scale = scale_h = min(avail_w / total_w, (avail_h - LAYOUT_MARGIN) / total_h)
        self.scale_factor = min(scale, scale_h)
        for r, row in enumerate(self.image_canvas):
            # a title may use its cell's share of the row, even when the (scaled) image is narrower
            title_share = (avail_w - GRID_SPACING * max(0, len(row) - 1)) // max(1, len(row))
            cell_widths = [int(w * scale) for w in col_widths[: len(row)]]
            for c, cell in enumerate(row):
                if cell is None or cell.get("natural_size") is None or cell.get("content") is None:
                    continue
                width, height = cell["natural_size"]
                cell["title_width"] = max(40, int(width * scale), title_share)
                title_w = set_cell_title(cell)
                cell_widths[c] = max(cell_widths[c], int(title_w))
                kind = cell.get("kind")
                if kind == "text":
                    dpg.configure_item(cell["content"], wrap=max(40, int(width * scale)))
                else:
                    dpg.configure_item(
                        cell["content"], width=max(1, int(width * scale)), height=max(1, int(height * scale_h))
                    )
                    if kind == "image":
                        place_image(cell, self.view)
            row_items = self._rows.get(r)
            if row_items is not None:
                row_w = sum(cell_widths) + GRID_SPACING * max(0, len(row) - 1)
                dpg.configure_item(row_items["spacer"], width=max(0, (avail_w - row_w) // 2))
        vertical_room = 0 if self.view.absolute else avail_h - int(total_h * scale_h) - LAYOUT_MARGIN
        dpg.configure_item(self.grid_vspacer, height=max(0, vertical_room // 2))

    # ------------------------------------------------------ zoom & pan (images)
    def image_cells(self) -> List[Dict[str, Any]]:
        return [
            cell
            for row in self.image_canvas or []
            for cell in row
            if cell is not None and cell.get("kind") == "image" and cell.get("drawn_image") is not None
        ]

    def apply_view(self):
        """Redraw every image cell with the shared zoom/pan state."""
        for cell in self.image_cells():
            place_image(cell, self.view)

    def set_view_mode(self, mode: str):
        """ "fit" (default) or "1:1" (cells at native image size) for every image cell (zoom/pan reset).

        1:1 grows the viewport to fit the native-size images; going back to
        fit restores the previous viewport size.
        """
        was_absolute = self.view.absolute
        self.view.set_mode(mode)
        self._grow_request = None
        self._grid_slack = list(GRID_SLACK)
        if self.view.absolute and not was_absolute:
            self._size_before_actual = self._viewport_outer_size()
        elif not self.view.absolute and self._size_before_actual is not None:
            previous, self._size_before_actual = self._size_before_actual, None
            self._resize_viewport(*previous)
        self.relayout()  # the cell sizes depend on the mode
        self.apply_view()

    def _can_resize_viewport(self) -> bool:
        requested = self.window_size
        full_or_max = isinstance(requested, str)  # "fullscreen" / "maximized"
        full_screen = self.main_gui is not None and getattr(self.main_gui, "full_screen_toggle", False)
        return self.viewport_ready and not full_or_max and not full_screen

    def _viewport_outer_size(self) -> Optional[Tuple[int, int]]:
        if not self._can_resize_viewport():
            return None
        return int(dpg.get_viewport_width()), int(dpg.get_viewport_height())

    def _resize_viewport(self, width: int, height: int):
        """Resize the viewport (outer size); the resize callback relays the layout out."""
        if not self._can_resize_viewport():
            return
        dpg.set_viewport_width(int(width))
        dpg.set_viewport_height(int(height))

    def _grow_viewport(self, client_w: int, client_h: int):
        """Grow (never shrink) the viewport so its client area is at least client_w x client_h.

        Idempotent: the reported client size lags a resize by a few frames, so
        the target only depends on the requested size, not on the current one.
        """
        if not self._can_resize_viewport():
            return
        width, height = int(dpg.get_viewport_width()), int(dpg.get_viewport_height())
        target = (max(width, client_w + self._decoration[0]), max(height, client_h + self._decoration[1]))
        if target == (width, height):
            return
        if self._grow_request is not None and (width, height) != self._grow_request:
            return  # the window manager did not grant the last request (screen limit): keep the scrollbars
        self._grow_request = target
        self._resize_viewport(*target)

    def _fit_grid_to_content(self):
        """Called every frame at 1:1: enlarge the grid by what its cells still
        overflow (child window paddings and item spacings the layout misses)."""
        if not self.view.absolute or not self.viewport_ready:
            return
        if self._frames_to_settle > 0:
            self._frames_to_settle -= 1  # the grid still shows (part of) the previous layout
            return
        scroll_max = dpg.get_item_state(self.grid_container).get("scroll_max") or (0, 0)
        overflow = [math.ceil(value) for value in scroll_max[:2]]
        if overflow[0] <= 0 and overflow[1] <= 0:
            return
        self._grid_slack = [slack + max(0, extra) for slack, extra in zip(self._grid_slack, overflow)]
        self.relayout()

    def reset_view(self):
        self.set_view_mode("fit")

    def zoom_by(self, factor: float, cell: Optional[Dict[str, Any]] = None, anchor=None):
        """Zoom around `anchor` (cell coordinates, default: center) of `cell` (default: first image)."""
        if cell is None:
            cells = self.image_cells()
            if not cells:
                return
            cell = cells[0]
        self.view.zoom_by(factor, image_box(cell), cell["natural_size"], anchor)
        self.apply_view()

    def image_cell_at(self, pos) -> Optional[Tuple[Dict[str, Any], Tuple[float, float]]]:
        """(cell, position in cell coordinates) of the image cell under `pos` (viewport coordinates)."""
        if not dpg.is_item_hovered(self.grid_container):
            # outside the grid, or the cell is covered by a detached panel
            return None
        for cell in self.image_cells():
            item = cell["content"]
            if not dpg.is_item_visible(item):
                continue
            x0, y0 = dpg.get_item_rect_min(item)
            width, height = image_box(cell)
            local = (pos[0] - x0, pos[1] - y0)
            if 0 <= local[0] < width and 0 <= local[1] < height:
                return cell, local
        return None

    def _mouse_target(self):
        if self.modal_shown():
            return None
        return self.image_cell_at(dpg.get_mouse_pos(local=False))

    def add_mouse_handlers(self, handler_registry):
        """Wheel zoom, left-drag pan and double-click fit on the image cells."""
        dpg.add_mouse_wheel_handler(callback=self.on_mouse_wheel, parent=handler_registry)
        dpg.add_mouse_click_handler(
            button=dpg.mvMouseButton_Left, callback=self.on_mouse_click, parent=handler_registry
        )
        dpg.add_mouse_move_handler(callback=self.on_mouse_move, parent=handler_registry)
        dpg.add_mouse_release_handler(
            button=dpg.mvMouseButton_Left, callback=self.on_mouse_release, parent=handler_registry
        )
        dpg.add_mouse_double_click_handler(
            button=dpg.mvMouseButton_Left, callback=self.on_mouse_double_click, parent=handler_registry
        )

    def on_mouse_wheel(self, _sender, delta, *_args):
        target = self._mouse_target()
        if target is None or not delta:
            return
        cell, local = target
        self.zoom_by(ZOOM_STEP ** float(delta), cell, local)

    def on_mouse_click(self, *_args):
        target = self._mouse_target()
        if target is None:
            self._drag = None
            return
        x, y = dpg.get_mouse_pos(local=False)[:2]
        self._drag = (target[0], (float(x), float(y)))

    def on_mouse_move(self, _sender, pos, *_args):
        if self._drag is None:
            return
        cell, last = self._drag
        if not dpg.is_mouse_button_down(dpg.mvMouseButton_Left) or not dpg.does_item_exist(cell["content"]):
            self._drag = None
            return
        self.view.pan_by(pos[0] - last[0], pos[1] - last[1], image_box(cell), cell["natural_size"])
        self._drag = (cell, (pos[0], pos[1]))
        self.apply_view()

    def on_mouse_release(self, *_args):
        self._drag = None

    def on_mouse_double_click(self, *_args):
        if self._mouse_target() is not None:
            self.reset_view()

    # ------------------------------------------------ columns of controls
    def _images_preferred_height(self, avail_w: int) -> int:
        """Height the image grid should keep before the controls take the room:
        native size at 1:1, otherwise the fitted size capped at FIT_PREFERRED_HEIGHT."""
        col_widths, row_heights = self.natural_grid_size()
        total_w = sum(col_widths) + GRID_SPACING * max(0, len(col_widths) - 1)
        total_h = sum(row_heights) + GRID_SPACING * max(0, len(row_heights) - 1)
        if total_w <= 0 or total_h <= 0:
            return MIN_GRID_HEIGHT
        if self.view.absolute:
            return total_h + LAYOUT_MARGIN + self._grid_slack[1]
        scale = min(1.0, avail_w / total_w, FIT_PREFERRED_HEIGHT / total_h)
        return max(MIN_GRID_HEIGHT, int(total_h * scale) + LAYOUT_MARGIN)

    def control_column_width(self) -> int:
        """Width of one column of the bottom controls (the full width with one column)."""
        width = self._client_size()[0] - LAYOUT_MARGIN - (SCROLLBAR_SIZE if self._bottom_scrolls else 0)
        count = self._control_columns
        return max(80, (width - CONTROL_COLUMN_GAP * (count - 1)) // count)

    def _measure_bottom_items(self) -> Optional[List[int]]:
        """Rendered height of each bottom item (row or panel) in a single column,
        from the distance between their tops; None before they are rendered."""
        if self._control_columns != 1 or self._columns_settle > 0 or not self.viewport_ready:
            return None
        tops = []
        for kind, item in self._bottom_items:
            target = item
            if kind == "row":  # table rows have no rect: use their label
                children = dpg.get_item_children(item, 1)
                if not children:
                    return None
                target = children[0]
            if not dpg.does_item_exist(target):
                return None
            tops.append(int(dpg.get_item_rect_min(target)[1]))
        container_top = int(dpg.get_item_rect_min(self.bottom_container)[1])
        container_h = self._measured_height(self.bottom_container)
        if container_h <= 0 or not tops or tops[0] < container_top:
            return None
        bottoms = tops[1:] + [container_top + container_h]
        heights = [bottom - top for top, bottom in zip(tops, bottoms)]
        return heights if all(h > 0 for h in heights) else None

    def _layout_control_columns(self, client_w: int, height_room: int) -> int:
        """Spread the bottom controls over the fewest columns that fit
        `height_room` (as many as the width holds when none does: they scroll).
        Returns the height of the controls."""
        measured = self._measure_bottom_items()
        if measured is not None:
            self._item_heights = measured
        heights = self._item_heights
        if heights is None or len(heights) < 2 or len(heights) != len(self._bottom_items):
            return self._measured_height(self.bottom_container)
        width_room = client_w - LAYOUT_MARGIN - SCROLLBAR_SIZE
        count = choose_column_count(
            heights,
            [MIN_CONTROL_COLUMN_WIDTH] * len(heights),
            width_room,
            height_room,
            column_gap=CONTROL_COLUMN_GAP,
        )
        self.set_control_columns(count)
        if self._columns_group is not None:
            for window in dpg.get_item_children(self._columns_group, 1) or []:
                dpg.configure_item(window, width=self.control_column_width())
        return int(math.ceil(columns_height(heights, self._control_columns)))

    def set_control_columns(self, count: int):
        """Move the bottom controls into `count` columns (in order, balanced heights)."""
        if count == self._control_columns:
            return
        self._release_columns()
        self._control_columns = 1
        self._columns_settle = LAYOUT_SETTLE_FRAMES
        if count <= 1 or self._item_heights is None:
            return
        columns = split_into_columns(self._item_heights, count)
        if len(columns) < 2:
            return
        self._control_columns = len(columns)
        self._columns_group = dpg.add_group(
            parent=self.bottom_container, horizontal=True, horizontal_spacing=CONTROL_COLUMN_GAP
        )
        width = self.control_column_width()
        for column in columns:
            window = dpg.add_child_window(
                parent=self._columns_group, width=width, auto_resize_y=True, border=False, no_scrollbar=True
            )
            table = None
            for index in column:
                kind, item = self._bottom_items[index]
                if kind == "row":
                    if table is None:
                        table = self._new_controls_table(window)
                    dpg.move_item(item, parent=table)
                else:
                    table = None
                    dpg.move_item(item, parent=window)
        if self._bottom_table is not None:
            dpg.configure_item(self._bottom_table, show=False)  # emptied

    def _new_controls_table(self, parent):
        """Empty copy of the ungrouped controls table (same label column)."""
        table = dpg.add_table(parent=parent, header_row=False, policy=dpg.mvTable_SizingStretchProp)
        label_width = 100.0
        if self._bottom_table is not None:
            columns = dpg.get_item_children(self._bottom_table, 0)
            if columns:
                label_width = dpg.get_item_configuration(columns[0]).get("init_width_or_weight", label_width)
        dpg.add_table_column(parent=table, width_fixed=True, init_width_or_weight=label_width)
        dpg.add_table_column(parent=table, width_stretch=True, init_width_or_weight=1.0)
        return table

    def _release_columns(self):
        """Back to a single column: every bottom item in its original container, in order."""
        if self._columns_group is None:
            return
        for kind, item in self._bottom_items:
            if kind == "row" and self._bottom_table is not None:
                dpg.move_item(item, parent=self._bottom_table)
            else:
                dpg.move_item(item, parent=self.bottom_container)
        if self._bottom_table is not None:
            dpg.configure_item(self._bottom_table, show=True)
        dpg.delete_item(self._columns_group)
        self._columns_group = None

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
            # leave room for the scrollbar of the controls area when it shows
            return self._client_size()[0] - LAYOUT_MARGIN - (SCROLLBAR_SIZE if self._bottom_scrolls else 0)

        def column_width() -> int:
            return self.control_column_width()

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
            row = builder.create_control_row(ctrl, self.bottom_container)
            if row is not None:
                self._bottom_items.append(("row", row))
                self._bottom_table = dpg.get_item_parent(row)
        for panel in panels_by_position["bottom"]:
            self._bottom_items.append(("panel", builder.build_panel(panel, self.bottom_container, column_width)))
        for panel in detached_panels:
            builder.build_detached_window(panel)
        # ImGui quirk: an empty group grows (by the scroll offset) once its window scrolls
        dpg.configure_item(self.top_container, show=bool(dpg.get_item_children(self.top_container, 1)))
        dpg.configure_item(self.bottom_scroll, show=bool(dpg.get_item_children(self.bottom_container, 1)))

    def on_detached_closed(self, sender, *_args):
        if sender in self.detached_windows:
            self.detached_windows.remove(sender)

    def text_entry_focused(self) -> bool:
        return any(dpg.does_item_exist(item) and dpg.is_item_focused(item) for item in self.prompt_widgets)

    def modal_shown(self) -> bool:
        """Whether the file dialog or the message window is open (both are modal)."""
        return any(
            item is not None and dpg.does_item_exist(item) and dpg.is_item_shown(item)
            for item in (self._file_dialog, self._message_window)
        )

    def tick_timers(self):
        """Called every frame: tick the timers, then run at most one pending refresh."""
        now = time.time()
        for timer in self.timers:
            timer.tick(now)
        self._fit_grid_to_content()
        if self._columns_settle > 0:
            self._columns_settle -= 1
            if self._columns_settle == 0:
                self.relayout()  # measure the controls in their new place
        if self._refresh_pending:
            self.refresh()

    def request_refresh(self):
        """Mark the pipeline dirty: the render loop (tick_timers) runs it once
        per frame, however many widget callbacks fired in between."""
        self._refresh_pending = True

    def set_status(self, text: str):
        """Show `text` in the status line at the bottom of the window."""
        dpg.set_value(self.status_text, text)

    def update_label(self, idx):
        if idx in self.name_label:
            dpg.set_value(self.name_label[idx], f"{self.ctrl[idx].name}")

    def update_parameter(self, idx, value):
        """Apply a new value (expressed in the control's own domain) and refresh."""
        self.ctrl[idx].update(value)
        self.update_label(idx)
        self.request_refresh()

    def key_update_parameter(self, idx, down):
        """Required implementation for keyboard sliders update"""
        if down:
            self.ctrl[idx].on_key_down()
        else:
            self.ctrl[idx].on_key_up()
        if idx in self.widget_list:
            self.widget_list[idx].reset()
        self.request_refresh()

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
        tooltip = dpg.add_tooltip(parent=title, show=False)  # full title, shown only when it is elided
        tooltip_text = dpg.add_text("", parent=tooltip)
        self.image_canvas[row][col] = {  # type: ignore[index]
            "cell": cell_group,
            "title": title,
            "title_tooltip": tooltip,
            "title_tooltip_text": tooltip_text,
            "full_title": "",
            "title_width": None,
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
        set_cell_title(cell, self.get_current_style(row, col).get("title", ""))

    @staticmethod
    def convert_image(out_im):
        if isinstance(out_im, np.ndarray) and out_im.ndim > 1:
            return out_im.clip(0.0, 1.0).astype(np.float32, copy=False)
        return out_im

    def refresh(self):
        """Run the pipeline now and display the results.

        A filter raising (FilterError) does not escape: the error is shown in
        the window (cell + status line) and the next good run restores it.
        """
        self._refresh_pending = False
        if self.pipeline is not None:
            try:
                out = self.pipeline.run()
            except FilterError as error:
                self.show_error(error)
            else:
                self._clear_error_cells()
                self.last_error = None
                self.refresh_display(out)
                self.set_status(format_run_status(self.pipeline.last_run_report))
        if self._needs_layout:
            self.relayout()

    def show_error(self, error: FilterError):
        """Display a pipeline error in the window instead of raising."""
        self.last_error = error
        for row, col in self.error_cell_positions(error):
            cell = self.image_canvas[row][col]  # type: ignore[index]
            if cell.get("kind") != "text":
                clear_cell_content(cell)
            update_text_cell(cell, format_error_message(error))
            dpg.configure_item(cell["content"], color=ERROR_COLOR)
            cell["kind"] = "text"
            cell["error"] = True
            self._needs_layout = True
        original = error.original_error
        self.set_status(f"error in {error.filter_name}: {type(original).__name__}: {original}")

    def _clear_error_cells(self):
        """Drop the error texts: the next display rebuilds these cells."""
        for row in self.image_canvas or []:
            for cell in row:
                if cell is not None and cell.pop("error", False):
                    clear_cell_content(cell)
                    self._needs_layout = True

    # ------------------------------------------------------- menu & dialogs
    def add_menu_bar(self, actions_by_menu: Dict[str, List[Action]], callback: Callable):
        """Menu bar of the primary window; each item passes its Action as user_data."""
        self.menu_bar = dpg.add_menu_bar(parent=self.root)
        for group, actions in actions_by_menu.items():
            menu = dpg.add_menu(label=group, parent=self.menu_bar)
            for action in actions:
                self.menu_items[action.name] = dpg.add_menu_item(
                    label=action.label,
                    shortcut=action.key.upper(),
                    parent=menu,
                    callback=callback,
                    user_data=action,
                )

    def open_file_dialog(
        self,
        title: str,
        save: bool,
        extensions: List[str],
        default_name: str,
        on_path: Callable[[Path], None],
    ):
        """Modal file dialog; `on_path(path)` runs when a file is chosen (nothing on cancel)."""
        if self._file_dialog is not None and dpg.does_item_exist(self._file_dialog):
            dpg.delete_item(self._file_dialog)

        def on_choice(_sender, app_data, _user_data):
            dpg.configure_item(dialog, show=False)
            chosen = app_data.get("file_path_name") if isinstance(app_data, dict) else None
            if chosen:
                on_path(Path(chosen))

        width, height = FILE_DIALOG_SIZE
        dialog = dpg.add_file_dialog(
            label=title,
            callback=on_choice,
            cancel_callback=lambda *_args: dpg.configure_item(dialog, show=False),
            modal=True,
            directory_selector=False,
            default_filename=Path(default_name).stem if save else "",
            width=width,
            height=height,
            show=True,
        )
        for extension in extensions:
            dpg.add_file_extension(extension, parent=dialog)
        self._file_dialog = dialog
        return dialog

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
