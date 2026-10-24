import logging
import sys
from typing import Any, Callable, List, Optional

import numpy as np

from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.graphical.qt_audio import QtAudioPlayer

# Qt binding detection lives in qt_backend (raises ModuleNotFoundError
# without a Qt binding, which choose_backend relies on).
from interactive_pipe.graphical.qt_backend import (  # noqa: F401
    MPL_SUPPORT,
    PYQTVERSION,
    Curve,
    Figure,
    FigureCanvas,
    QApplication,
    QAudioOutput,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QImage,
    QLabel,
    QMediaContent,
    QMediaPlayer,
    QMessageBox,
    QPixmap,
    QPushButton,
    Qt,
    QtFrameBase,
    QTimer,
    QtWidgetBase,
    QUrl,
    QVBoxLayout,
    QWidget,
    SingleCurve,
    Table,
)
from interactive_pipe.graphical.qt_control import ControlFactory
from interactive_pipe.graphical.qt_image import (
    numpy_to_pixmap,
    signal_to_curve,
    update_curve_cell,
    update_table_cell,
)
from interactive_pipe.graphical.qt_panels import QtPanelBuilder
from interactive_pipe.graphical.qt_viewer import ImageView, ViewSync

# Re-exported: interactive_pipe.graphical.qt_gui.CollapsibleBox etc. are public paths
from interactive_pipe.graphical.qt_widgets import CollapsibleBox, DetachedPanelWindow  # noqa: F401
from interactive_pipe.graphical.window import InteractivePipeWindow, display_kind
from interactive_pipe.headless.control import Control, TimeControl
from interactive_pipe.headless.keyboard import KeyboardControl
from interactive_pipe.headless.panel import Panel
from interactive_pipe.headless.pipeline import HeadlessPipeline


def _normalize_output_grid(_out):
    """Same [row][col] layout as InteractivePipeWindow.refresh_display builds."""
    if _out is None:
        return None
    if isinstance(_out, tuple):
        _out = [list(_out)]
    return [list(row) if isinstance(row, list) else [row] for row in _out]


def _format_pixel_value(value) -> str:
    if isinstance(value, tuple):
        return "(" + ", ".join(f"{v:.4g}" for v in value) + ")"
    return f"{value:.4g}"


class InteractivePipeQT(InteractivePipeGUI):
    def init_app(self, **kwargs):
        if not QApplication.instance():
            self.app = QApplication(sys.argv)
        else:
            self.app = QApplication.instance()

        self.window = MainWindow(
            controls=self.controls,
            name=self.name,
            pipeline=self.pipeline,
            size=self.size,
            main_gui=self,
            **kwargs,
        )
        self.set_default_key_bindings()

        if self.audio:
            # AudioBindings defaults are no-ops, so the pipeline can run
            # before the real player exists.
            # Defer audio initialization to avoid PipeWire sync blocking
            QTimer.singleShot(100, self.audio_player)

    def run(self) -> list:
        if not self.pipeline._PipelineCore__initialized_inputs:  # type: ignore[reportAttributeAccessIssue]
            raise RuntimeError("Did you forget to initialize the pipeline inputs?")
        self.window.refresh()
        if self.app is not None:
            self.app.exec()
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
                "f1": self.show_help,
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

    def close(self):
        """close GUI"""
        if self.app is not None:
            self.app.quit()

    def reset_parameters(self):
        """reset sliders to default parameters"""
        super().reset_parameters()
        for widget_idx, ctrl in self.window.ctrl.items():
            if isinstance(ctrl, TimeControl):
                # self.suspend_resume_timer(True)
                # self.time_playing = False
                self.start_time = None  # Reset the timer
            ctrl.value = ctrl.value_default
        self.window.reset_sliders()

    def load_parameters(self):
        """import parameters dictionary from a yaml/json file on disk"""
        # HeadlessPipeline.parameters (set by import_tuning) writes the loaded
        # values back into the connected controls; the widgets just need syncing.
        super().load_parameters()
        self.window.reset_sliders()

    def print_message(self, message_list: List[str]):
        print("\n".join(message_list))
        QMessageBox.about(self.window, self.name, "\n".join(message_list))

    def toggle_full_screen(self):
        """toggle full screen"""
        if not hasattr(self, "full_screen_toggle"):
            self.full_screen_toggle = self.window.full_screen_flag
        self.full_screen_toggle = not self.full_screen_toggle
        if self.full_screen_toggle:
            # Go to fullscreen
            self.window.full_screen()
        else:
            window_size = self.window.window_size
            if isinstance(window_size, str) and "full" in window_size.lower():
                # Special case where the window naturally goes to fullscreen since user defined it...
                # Force to go back to normal
                self.window.showNormal()
            else:  # Go back to normal size
                self.window.update_window()

    # ---------------------------- AUDIO FEATURE ----------------------------------------

    def audio_player(self):
        self.player = QtAudioPlayer()
        audio = self.pipeline.framework_state.audio
        audio.set_audio = self.player.set_audio
        audio.play = self.player.play
        audio.pause = self.player.pause
        audio.stop = self.player.stop


class MainWindow(QtWidgetBase, InteractivePipeWindow):  # type: ignore[reportGeneralTypeIssues]
    key_mapping_dict = {
        Qt.Key.Key_Up: KeyboardControl.KEY_UP,
        Qt.Key.Key_Down: KeyboardControl.KEY_DOWN,
        Qt.Key.Key_Left: KeyboardControl.KEY_LEFT,
        Qt.Key.Key_Right: KeyboardControl.KEY_RIGHT,
        Qt.Key.Key_PageUp: KeyboardControl.KEY_PAGEUP,
        Qt.Key.Key_PageDown: KeyboardControl.KEY_PAGEDOWN,
        Qt.Key.Key_F1: "f1",
        Qt.Key.Key_F2: "f2",
        Qt.Key.Key_F3: "f3",
        Qt.Key.Key_F4: "f4",
        Qt.Key.Key_F5: "f5",
        Qt.Key.Key_F6: "f6",
        Qt.Key.Key_F7: "f7",
        Qt.Key.Key_F8: "f8",
        Qt.Key.Key_F9: "f9",
        Qt.Key.Key_F10: "f10",
        Qt.Key.Key_F11: "f11",
        Qt.Key.Key_F12: "f12",
        Qt.Key.Key_Space: KeyboardControl.KEY_SPACEBAR,
    }
    # (row, col, x, y, value) when the mouse hovers an image cell; value is the
    # raw pipeline output at that pixel (None outside). None -> tooltip readout.
    on_pixel_hover: Optional[Callable[[int, int, int, int, Any], None]] = None

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
        QWidget.__init__(self, *args, **kwargs)
        InteractivePipeWindow.__init__(self, name=name, pipeline=pipeline, size=size)
        self.main_gui = main_gui
        self.setWindowTitle(self.name)

        # Track detached panel windows
        self.detached_windows = []
        # Set by QtPanelBuilder when a TimeControl widget is created
        self.timer: Optional[QTimer] = None

        # Create main vertical layout (replaces QFormLayout)
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Create containers for panels at different positions
        self.top_panels_layout = QVBoxLayout()
        self.left_panels_layout = QVBoxLayout()
        self.right_panels_layout = QVBoxLayout()
        self.bottom_panels_layout = QVBoxLayout()

        # Create image grid layout
        self.image_grid_layout = QGridLayout()

        # Build middle section (horizontal: left panels | images | right panels)
        middle_layout = QHBoxLayout()
        if center:
            # Create QHBoxLayout for horizontal centering
            horizontal_centering_layout = QHBoxLayout()
            horizontal_centering_layout.addStretch()  # Add stretch to left side
            horizontal_centering_layout.addLayout(self.image_grid_layout)
            horizontal_centering_layout.addStretch()  # Add stretch to right side

            # Create QVBoxLayout for vertical centering
            vertical_centering_layout = QVBoxLayout()
            vertical_centering_layout.addStretch()  # Add stretch to top
            vertical_centering_layout.addLayout(horizontal_centering_layout)
            vertical_centering_layout.addStretch()  # Add stretch to bottom

            # Add left panels, centered images, right panels to middle layout
            middle_layout.addLayout(self.left_panels_layout)
            middle_layout.addLayout(vertical_centering_layout)
            middle_layout.addLayout(self.right_panels_layout)
        else:
            # No centering - simpler layout
            middle_layout.addLayout(self.left_panels_layout)
            middle_layout.addLayout(self.image_grid_layout)
            middle_layout.addLayout(self.right_panels_layout)

        # Assemble main layout: top panels | middle (left | images | right) | bottom panels
        main_layout.addLayout(self.top_panels_layout)
        main_layout.addLayout(middle_layout)
        main_layout.addLayout(self.bottom_panels_layout)

        self.init_sliders(controls)
        # if self.pipeline._PipelineCore__initialized_inputs:
        #     # cannot refresh the pipeline if no input has been provided! ... not ok for inputless pipeline though!
        #     self.refresh()
        # # You will refresh the window  at the app level, only when running.
        # # no need to run the pipeline engine to initalize the GUI
        self.window_size = size
        self.full_screen_flag = False

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.show()

    @property
    def window_size(self):
        return self._size

    @window_size.setter
    def window_size(self, _size):
        if isinstance(_size, str):
            if "full" not in _size.lower() and "max" not in _size.lower():
                raise ValueError(f"size={_size} can only be among (full, fullscreen, maximized, max, maximum)")
        self._size = _size
        self.update_window()

    def update_window(self):
        self.full_screen_flag = False
        requested = self.window_size
        if requested is None:
            self.showNormal()
            return
        if isinstance(requested, str):
            if "max" in requested.lower():
                self.maximize_screen()
            if "full" in requested.lower():
                self.full_screen()
        else:
            self.showNormal()
            if isinstance(requested, int):
                self.setMinimumWidth(requested)
            elif isinstance(requested, (tuple, list)):
                self.setMinimumWidth(requested[0])
                self.setMinimumHeight(requested[1])

    def full_screen(self):
        self.showFullScreen()
        self.full_screen_flag = True

    def maximize_screen(self):
        self.showMaximized()
        self.full_screen_flag = False

    def keyPressEvent(self, event):
        mapped_str = None

        current_key = event.key()
        for qt_key, str_mapping in self.key_mapping_dict.items():
            if current_key == qt_key:
                mapped_str = str_mapping
                logging.debug(f"matched Qt key{mapped_str}")
        if mapped_str is None:
            mapped_str = event.text()
        if self.main_gui is not None:
            self.main_gui.on_press(mapped_str, refresh_func=self.refresh)  # type: ignore[reportOptionalMemberAccess]

    def _build_element_widget(self, element, control_factory: ControlFactory) -> Optional[QWidget]:
        """Build widget for an element (Panel or Control). Delegates to QtPanelBuilder."""
        return QtPanelBuilder(self, control_factory).build_element_widget(element)

    def _build_panel_widget(self, panel: Panel, control_factory: ControlFactory) -> QWidget:
        """Recursively build Qt widget for a Panel. Delegates to QtPanelBuilder.

        Keep this signature stable: DetachedPanelWindow calls it.
        """
        return QtPanelBuilder(self, control_factory).build_panel_widget(panel)

    def _create_control_widget(self, ctrl: Control, control_factory: ControlFactory) -> Optional[QWidget]:
        """Create a single control widget row. Delegates to QtPanelBuilder."""
        return QtPanelBuilder(self, control_factory).create_control_widget(ctrl)

    def init_sliders(self, controls: List[Control]):
        self.ctrl = {}
        self.result_label = {}
        self.name_label = {}
        self.widget_list = {}
        control_factory = ControlFactory()
        vertical_spacing = 1  # Decrease this value to reduce vertical space between sliders
        # Set spacing on all panel layouts
        self.top_panels_layout.setSpacing(vertical_spacing)
        self.left_panels_layout.setSpacing(vertical_spacing)
        self.right_panels_layout.setSpacing(vertical_spacing)
        self.bottom_panels_layout.setSpacing(vertical_spacing)

        # Collect all panels and build hierarchy
        root_panels = set()  # Use set to avoid duplicates
        ungrouped_controls = []

        for ctrl in controls:
            self.ctrl[ctrl.name] = ctrl
            if ctrl.panel is None:
                ungrouped_controls.append(ctrl)
            else:
                # Find the root panel by traversing up the parent chain
                root_panel = ctrl.panel.get_root()
                root_panels.add(root_panel)

        # Separate detached and regular panels
        detached_panels = []
        regular_panels = []
        for panel in root_panels:
            if panel.detached:
                detached_panels.append(panel)
            else:
                regular_panels.append(panel)

        # Group regular panels by position
        panels_by_position = {"top": [], "left": [], "right": [], "bottom": []}
        for panel in regular_panels:
            pos = panel.position or "bottom"  # Default to bottom for backward compatibility
            panels_by_position[pos].append(panel)

        # Render panels to appropriate containers based on position
        for panel in panels_by_position["top"]:
            panel_widget = self._build_panel_widget(panel, control_factory)
            self.top_panels_layout.addWidget(panel_widget)

        for panel in panels_by_position["left"]:
            panel_widget = self._build_panel_widget(panel, control_factory)
            self.left_panels_layout.addWidget(panel_widget)

        for panel in panels_by_position["right"]:
            panel_widget = self._build_panel_widget(panel, control_factory)
            self.right_panels_layout.addWidget(panel_widget)

        # Render ungrouped controls and bottom panels
        for ctrl in ungrouped_controls:
            row_widget = self._create_control_widget(ctrl, control_factory)
            if row_widget is not None:
                self.bottom_panels_layout.addWidget(row_widget)

        for panel in panels_by_position["bottom"]:
            panel_widget = self._build_panel_widget(panel, control_factory)
            self.bottom_panels_layout.addWidget(panel_widget)

        # Create detached windows for detached panels (position is ignored for detached)
        for panel in detached_panels:
            detached_window = DetachedPanelWindow(panel, self, control_factory)
            self.detached_windows.append(detached_window)

    def update_label(self, idx):
        # pass
        val = self.ctrl[idx].value
        val_to_print = val
        if isinstance(val, float):
            val_to_print = f"{val:.3e}"
        if idx in self.result_label.keys():
            self.result_label[idx].setText(f"{val_to_print}")
        if idx in self.name_label.keys():
            self.name_label[idx].setText(f"{self.ctrl[idx].name}")

    def update_parameter(self, idx, value):
        """Apply a new value (expressed in the control's own domain) and refresh.

        Widgets (qt_control) and the timer convert to that domain themselves:
        float for float sliders, the chosen string for dropdowns, bool for
        tick boxes.
        """
        self.ctrl[idx].update(value)
        self.update_label(idx)
        self.refresh()

    def key_update_parameter(self, idx, down):
        """Required implementation for keyboard sliders update"""
        if down:
            self.ctrl[idx].on_key_down()
        else:
            self.ctrl[idx].on_key_up()
        # self.update_label(idx)
        self.refresh()

    # --- image grid: ImageView cells (fit / synced zoom & pan / pixel readout) ---
    def _view_sync(self) -> ViewSync:
        sync = getattr(self, "_image_view_sync", None)
        if sync is None:
            sync = ViewSync()
            self._image_view_sync = sync
        return sync

    def _new_image_view(self, row, col) -> ImageView:
        view = ImageView(self, sync=self._view_sync())
        view.hover_callback = lambda x, y, value: self._on_view_hover(view, row, col, x, y, value)
        self.image_grid_layout.addWidget(view, 2 * row + 1, col)
        return view

    def _on_view_hover(self, view, row, col, x, y, value):
        if self.on_pixel_hover is not None:
            self.on_pixel_hover(row, col, x, y, value)
        else:
            view.setToolTip("" if value is None else f"({x}, {y}): {_format_pixel_value(value)}")

    def _expand_image_grid(self):
        """Give the image grid all the spare room (it is wrapped in centering
        stretches): image views then fit the window as the user resizes it."""
        child = self.image_grid_layout
        parent = child.parent()
        while isinstance(parent, (QHBoxLayout, QVBoxLayout)):
            parent.setStretchFactor(child, 1)
            child, parent = parent, parent.parent()

    def set_view_mode(self, mode: str):
        """ "fit" (default) or "1:1" for every image cell (zoom/pan reset)."""
        self._view_sync().set_mode(mode)

    def zoom_in(self):
        self._sync_zoom(True)

    def zoom_out(self):
        self._sync_zoom(False)

    def _sync_zoom(self, zoom_in: bool):
        views = self._view_sync().views
        if not views:
            return
        # zoom around the center of the first view: the state is shared anyway
        views[0].zoom_in() if zoom_in else views[0].zoom_out()

    def reset_view(self):
        self._view_sync().reset()

    def refresh_display(self, _out) -> None:
        # Keep the raw (float) outputs so the views report true pixel values;
        # convert_image only produces the 8-bit display copy.
        self._raw_outputs = _normalize_output_grid(_out)
        super().refresh_display(_out)

    def _raw_output(self, row, col) -> Any:
        grid = getattr(self, "_raw_outputs", None)
        try:
            return grid[row][col] if grid is not None else None
        except (IndexError, TypeError):
            return None

    def add_image_placeholder(self, row, col):
        ax_placeholder = None
        text_label = QLabel(text=f"{row} {col}")
        self.image_grid_layout.addWidget(text_label, 2 * row, col, alignment=Qt.AlignmentFlag.AlignCenter)
        image_view = self._new_image_view(row, col)
        self.image_canvas[row][col] = {  # type: ignore[reportOptionalSubscript]
            "image": image_view,
            "title": text_label,
            "ax_placeholder": ax_placeholder,
            "row": row,
            "col": col,
            "fit_window": True,
        }
        # cells share the window evenly; title rows keep their natural height
        self.image_grid_layout.setRowStretch(2 * row + 1, 1)
        self.image_grid_layout.setColumnStretch(col, 1)
        self._expand_image_grid()

    def delete_image_placeholder(self, img_widget_dict):
        for key in ("image", "title"):
            widget = img_widget_dict.get(key)
            if isinstance(widget, ImageView):
                widget.detach()
            if widget is not None:
                widget.setParent(None)
        row, col = img_widget_dict.get("row"), img_widget_dict.get("col")
        if row is not None and col is not None:
            self.image_grid_layout.setRowStretch(2 * row + 1, 0)
            self.image_grid_layout.setColumnStretch(col, 0)
        img_widget_dict["plot_object"] = None
        img_widget_dict["ax_placeholder"] = None

    def _reset_cell_widget(self, cell, row, col, new_kind):
        """Swap the cell widget when the output type changes between frames."""
        mpl_kinds = ("curve", "table")
        previous_kind = cell.get("kind")
        if previous_kind in mpl_kinds and new_kind in mpl_kinds:
            # same FigureCanvas, different artist: wipe the axes
            if cell.get("ax_placeholder") is not None:
                cell["ax_placeholder"].clear()
            cell["plot_object"] = None
            return
        if previous_kind in mpl_kinds or new_kind in mpl_kinds:
            # FigureCanvas <-> ImageView: drop the current widget, a fresh view is
            # created here and the canvas helpers recreate theirs on demand
            if isinstance(cell["image"], ImageView):
                cell["image"].detach()
            cell["image"].setParent(None)
            cell["plot_object"] = None
            cell["ax_placeholder"] = None
            cell["image"] = self._new_image_view(row, col)
        # image <-> text share the same ImageView (setText/set_image replace each other)

    def _fit_window_to_images(self):
        """Grow the window once so new image cells get their preferred size
        (views can shrink, so Qt no longer grows the window by itself)."""
        if self.full_screen_flag or self.isMaximized() or self.isFullScreen():
            return
        layout = self.layout()
        if layout is not None:
            layout.activate()
        hint = self.sizeHint()
        width, height = max(self.width(), hint.width()), max(self.height(), hint.height())
        screen = self.screen() if hasattr(self, "screen") else None
        if screen is not None:
            available = screen.availableGeometry()
            width, height = min(width, available.width()), min(height, available.height())
        if (width, height) != (self.width(), self.height()):
            self.resize(width, height)

    def update_image(self, image_array_original, row, col):
        cell = self.image_canvas[row][col]  # type: ignore[reportOptionalSubscript]
        if isinstance(image_array_original, np.ndarray) and len(image_array_original.shape) == 1:
            image_array_original = signal_to_curve(image_array_original)
        kind = display_kind(image_array_original)
        if cell.get("kind") not in (None, kind):
            self._reset_cell_widget(cell, row, col, kind)
        cell["kind"] = kind
        if isinstance(image_array_original, np.ndarray):
            shown: np.ndarray = image_array_original
            raw = self._raw_output(row, col)
            if not isinstance(raw, np.ndarray) or raw.shape[:2] != shown.shape[:2]:
                raw = shown
            cell["image"].set_image(numpy_to_pixmap(shown), raw)
            if cell.pop("fit_window", False):
                self._fit_window_to_images()
        elif MPL_SUPPORT and FigureCanvas is not None and isinstance(image_array_original, Curve):
            update_curve_cell(cell, self.image_grid_layout, row, col, image_array_original)
        elif MPL_SUPPORT and FigureCanvas is not None and isinstance(image_array_original, Table):
            update_table_cell(cell, self.image_grid_layout, row, col, image_array_original)
        elif isinstance(image_array_original, str):
            cell.pop("fit_window", None)
            cell["image"].setText(image_array_original)
        else:
            logging.warning(f"Unsupported output type for display: {type(image_array_original)}")
        # Title update stays unconditional and last
        cell["title"].setText(self.get_current_style(row, col).get("title", ""))

    @staticmethod
    def convert_image(out_im):
        if isinstance(out_im, np.ndarray) and len(out_im.shape) > 1:
            return (out_im.clip(0.0, 1.0) * 255).astype(np.uint8)
        else:
            return out_im

    def refresh(self):
        if self.pipeline is not None:
            out = self.pipeline.run()
            self.refresh_display(out)

    def reset_sliders(self):
        for widget_idx, ctrl in self.ctrl.items():
            if widget_idx in self.widget_list.keys():
                self.widget_list[widget_idx].reset()
            self.update_label(widget_idx)
        self.refresh()

    def closeEvent(self, event):
        """Handle main window close event - close all detached windows."""
        # Close all detached panel windows
        for detached_window in self.detached_windows:
            detached_window.close()
        self.detached_windows.clear()
        event.accept()
