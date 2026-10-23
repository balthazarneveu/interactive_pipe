"""Recursive panel/control building for the Dear PyGui backend.

``DpgPanelBuilder`` is stateless: every registry it touches (``widget_list``,
``name_label``, ``prompt_widgets``, ``timers``, ``detached_windows``,
``sized_items``) lives on the window.

Controls that belong to the same container are laid out in a two-column
table (fixed label column, stretching widget column) so their widgets line
up like the Qt rows. Panels become collapsing headers or framed child
windows that fill the width of their parent; grid rows
(``Panel.add_elements([[a, b], [c]])``) become horizontal groups whose cells
get an explicit width (stretching content inside an auto-sized Dear PyGui
child would otherwise grab the whole window), re-applied on viewport resize
through ``window.sized_items``; detached panels become floating windows.
"""

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from interactive_pipe.graphical.dpg_backend import dpg
from interactive_pipe.graphical.dpg_control import ControlFactory
from interactive_pipe.headless.control import Control, TimeControl
from interactive_pipe.headless.keyboard import KeyboardControl
from interactive_pipe.headless.panel import Panel

if TYPE_CHECKING:
    from interactive_pipe.graphical.dpg_gui import MainWindow

PANEL_TITLE_COLOR = (255, 200, 80, 255)
LABEL_CHAR_WIDTH = 7  # approximate pixel width of one character with the default font
LABEL_MIN_WIDTH = 60
LABEL_MAX_WIDTH = 160
GRID_GAP = 8  # pixels between the cells of a panel grid row
PANEL_PADDING = 16  # child window padding (both sides)
DETACHED_DEFAULT_SIZE = (360, 300)

WidthFn = Callable[[], int]


class DpgTimer:
    """Periodic callback driven from the render loop (Dear PyGui has no timer widget).

    ``tick(now)`` is called once per frame by the window and fires the
    callback when ``interval_ms`` elapsed since the previous firing.
    """

    def __init__(self, interval_ms: int, callback):
        self.interval_s = max(1, int(interval_ms)) / 1000.0
        self.callback = callback
        self.running = False
        self._last_fire: Optional[float] = None

    def start(self, now: Optional[float] = None):
        self.running = True
        self._last_fire = now

    def stop(self):
        self.running = False

    def tick(self, now: float) -> bool:
        """Fire the callback when due; returns True when it fired."""
        if not self.running:
            return False
        if self._last_fire is None:
            self._last_fire = now
        if now - self._last_fire < self.interval_s - 1e-9:
            return False
        self._last_fire = now
        self.callback()
        return True


class DpgPanelBuilder:
    def __init__(self, window: "MainWindow", control_factory: ControlFactory):
        self.window = window
        self.control_factory = control_factory
        self._tables: Dict[Any, Any] = {}  # container item -> 2-column controls table

    # ------------------------------------------------------------------ panels
    def build_element(self, element, parent, width_fn: WidthFn) -> Optional[Any]:
        if isinstance(element, Panel):
            return self.build_panel(element, parent, width_fn)
        if isinstance(element, Control):
            return self.create_control_row(element, parent)
        return None

    def build_panel(self, panel: Panel, parent, width_fn: WidthFn) -> Any:
        """Build the container of a panel inside ``parent`` and fill it. Returns the container.

        ``width_fn`` returns the width available to the panel (used to size grid cells).
        """
        if panel.collapsible:
            container = dpg.add_collapsing_header(
                label=panel.name or "", default_open=not panel.collapsed, parent=parent
            )
        else:
            container = dpg.add_child_window(parent=parent, auto_resize_y=True, border=True)
            if panel.name:
                dpg.add_text(panel.name, parent=container, color=PANEL_TITLE_COLOR)
                dpg.add_separator(parent=container)
        self.fill_panel(panel, container, width_fn)
        return container

    def fill_panel(self, panel: Panel, container, width_fn: WidthFn) -> None:
        """Add the child panels, grid rows and controls of ``panel`` to ``container``."""
        if panel.elements and isinstance(panel.elements[0], list):
            for row in panel.elements:
                if not isinstance(row, list) or not row:
                    continue
                row_group = dpg.add_group(horizontal=True, parent=container, horizontal_spacing=GRID_GAP)
                ncols = len(row)

                def cell_width(ncols=ncols, width_fn=width_fn) -> int:
                    return max(80, (width_fn() - PANEL_PADDING - GRID_GAP * (ncols - 1)) // ncols)

                for element in row:
                    slot = dpg.add_child_window(parent=row_group, width=cell_width(), auto_resize_y=True, border=False)
                    self.window.sized_items.append((slot, cell_width))
                    self.build_element(element, slot, cell_width)
        else:
            for element in panel.elements:
                self.build_element(element, container, width_fn)
        for ctrl in panel._controls:
            self.create_control_row(ctrl, container)

    def build_detached_window(self, panel: Panel) -> Any:
        """Open a floating window holding the panel; returns the window item."""
        width, height = panel.detached_size or DETACHED_DEFAULT_SIZE
        offset = 30 * len(self.window.detached_windows)
        window = dpg.add_window(
            label=panel.name or "Detached Panel",
            width=int(width),
            height=int(height),
            pos=(40 + offset, 60 + offset),
            on_close=self.window.on_detached_closed,
        )
        self.fill_panel(panel, window, lambda: int(width))
        self.window.detached_windows.append(window)
        return window

    # ---------------------------------------------------------------- controls
    def _controls_table(self, container, ctrl: Control):
        """One two-column table per container, created when its first control arrives."""
        table = self._tables.get(container)
        if table is not None and dpg.does_item_exist(table):
            return table
        label_width = min(LABEL_MAX_WIDTH, max(LABEL_MIN_WIDTH, LABEL_CHAR_WIDTH * len(ctrl.name) + 12))
        table = dpg.add_table(parent=container, header_row=False, policy=dpg.mvTable_SizingStretchProp)
        dpg.add_table_column(parent=table, width_fixed=True, init_width_or_weight=label_width)
        dpg.add_table_column(parent=table, width_stretch=True, init_width_or_weight=1.0)
        self._tables[container] = table
        return table

    def create_control_row(self, ctrl: Control, container) -> Optional[Any]:
        """Create the label + widget row of a control; returns the row item or None when nothing is shown."""
        window = self.window
        if isinstance(ctrl, KeyboardControl):
            if window.main_gui is not None:
                window.main_gui.bind_keyboard_slider(ctrl, window.key_update_parameter)
            return None
        if isinstance(ctrl, TimeControl):
            self._plug_time_control(ctrl)
            return None
        widget_wrapper = self.control_factory.create_control(ctrl, window.update_parameter)
        if widget_wrapper is None:
            return None
        if ctrl._type is str and ctrl.icons is not None and ctrl.filter_to_connect is not None:
            # icon bars re-trigger the same choice: never serve it from the cache
            ctrl.filter_to_connect.cache = False
            ctrl.filter_to_connect.cache_mem = None
        table = self._controls_table(container, ctrl)
        row = dpg.add_table_row(parent=table)
        label = dpg.add_text(ctrl.name, parent=row)
        widget_wrapper.create(row)
        window.widget_list[ctrl.name] = widget_wrapper
        window.name_label[ctrl.name] = label
        window.prompt_widgets.extend(widget_wrapper.widgets)
        return row

    def _plug_time_control(self, ctrl: TimeControl) -> None:
        window = self.window
        if window.main_gui is None:
            return
        timer = DpgTimer(ctrl.update_interval_ms, lambda: None)

        def suspend_resume_timer(suspend: bool):
            if suspend:
                logging.debug("Suspend timer")
                timer.stop()
            else:
                logging.debug("Resume timer")
                timer.start()

        window.main_gui.suspend_resume_timer = suspend_resume_timer
        timer.callback = window.main_gui.plug_timer_control(ctrl, window.update_parameter, suspend_resume_timer)
        timer.start()
        window.timers.append(timer)
        window.timer = timer
