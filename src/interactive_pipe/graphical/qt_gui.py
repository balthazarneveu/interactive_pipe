import importlib
import logging
import sys
import threading
import time
from functools import partial
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from interactive_pipe.core.engine import FilterError
from interactive_pipe.data_objects.image import Image
from interactive_pipe.graphical import qt_audio_stream
from interactive_pipe.graphical.actions import Action
from interactive_pipe.graphical.columns import choose_column_count, split_into_columns
from interactive_pipe.graphical.display import display_data, figure_of, heatmap_geometry, rasterize_figure
from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.graphical.icon import icon_path
from interactive_pipe.graphical.pointer_input import Gesture, PointerTargets, overlay_items, to_fraction
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
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QIcon,
    QImage,
    QLabel,
    QMediaContent,
    QMediaPlayer,
    QMenuBar,
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
    quiet_offscreen_messages,
)
from interactive_pipe.graphical.qt_control import ControlFactory
from interactive_pipe.graphical.qt_image import (
    discard_widget,
    numpy_to_pixmap,
    signal_to_curve,
    update_curve_cell,
    update_table_cell,
)
from interactive_pipe.graphical.qt_panels import QtPanelBuilder
from interactive_pipe.graphical.qt_runner import PipelineRunner
from interactive_pipe.graphical.qt_viewer import ImageView, PointerHandler, ViewSync

# Re-exported: interactive_pipe.graphical.qt_gui.CollapsibleBox etc. are public paths
from interactive_pipe.graphical.qt_widgets import (  # noqa: F401
    CollapsibleBox,
    ControlsContent,
    ControlsScrollArea,
    DetachedPanelWindow,
    ElidedLabel,
)
from interactive_pipe.graphical.value_format import format_value
from interactive_pipe.graphical.window import (
    InteractivePipeWindow,
    display_kind,
    format_error_message,
    format_run_status,
)
from interactive_pipe.headless.control import Control, TimeControl
from interactive_pipe.headless.keyboard import KeyboardControl
from interactive_pipe.headless.panel import Panel
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.headless.pointer import pointer_controls
from interactive_pipe.headless.timeline import TimelineControl

# seconds within which a smaller size after a resize request is the window
# manager's answer (rather than the user resizing the window)
RESIZE_ANSWER_DELAY = 1.0
NO_LIMIT = 1 << 24  # pixels: a dimension the window manager never shrank
CONTROL_COLUMN_GAP = 16  # pixels between the columns of controls


def layout_widgets(layout) -> List[QWidget]:
    """Widgets directly held by `layout`, in order."""
    widgets = []
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget() if item is not None else None
        if widget is not None:
            widgets.append(widget)
    return widgets


def _normalize_output_grid(_out):
    """Same [row][col] layout as InteractivePipeWindow.refresh_display builds."""
    if _out is None:
        return None
    if isinstance(_out, tuple):
        _out = [list(_out)]
    return [list(row) if isinstance(row, list) else [row] for row in _out]


def _figure_positions(grid) -> dict:
    """(row, col) -> matplotlib figure output of a normalized output grid."""
    return {
        (row, col): content
        for row, cells in enumerate(grid or [])
        for col, content in enumerate(cells)
        if figure_of(content) is not None
    }


def _rasterize_figures(out, layout, boxes=None, pixel_ratio=1.0):
    """`out` with matplotlib figure outputs replaced by their raster (same
    structure), using each output's ``layout.style(dpi=...)``, at the size of
    their cell (`boxes`: (row, col) -> view size) when known."""
    outputs, styles = layout

    def name_at(*index):
        try:
            value = outputs
            for position in index:
                value = value[position]
            return value
        except (IndexError, TypeError, KeyError):
            return None

    def convert(content, *index):
        if figure_of(content) is None:
            return content
        name = name_at(*index)
        style = styles.get(name) if isinstance(name, (str, int)) else None
        box = (boxes or {}).get(index if len(index) == 2 else (0, index[0]))
        return rasterize_figure(content, (style or {}).get("dpi"), box, pixel_ratio)

    is_grid = isinstance(out, list) and any(isinstance(cells, (list, tuple)) for cells in out)
    if is_grid:
        return [
            [convert(content, row, col) for col, content in enumerate(cells)]
            if isinstance(cells, (list, tuple))
            else convert(cells, row)
            for row, cells in enumerate(out)
        ]
    if isinstance(out, (list, tuple)):
        return type(out)(convert(content, col) for col, content in enumerate(out))
    return convert(out, 0)


class _CellPointerHandler(PointerHandler):
    """Gestures of the ImageView of cell (row, col), in fractions of its data area."""

    def __init__(self, window, view, row: int, col: int) -> None:
        self.window, self.view, self.cell = window, view, (row, col)

    def _fraction(self, u: float, v: float):
        size = self.window._pointer_data_size(self.view, *self.cell)
        return None if size is None else to_fraction(u, v, size)

    def _gesture(self) -> Gesture:
        gesture = getattr(self.window, "pointer_gesture", None)
        if gesture is None:
            gesture = self.window.pointer_gesture = Gesture()
        return gesture

    def press(self, u, v, screen, shift):
        targets = getattr(self.window, "pointer_targets", None)
        fraction = self._fraction(u, v)
        if targets is None or fraction is None:
            return None
        gesture = self._gesture()
        if not gesture.press(targets, self.cell, fraction, screen, shift):
            return None
        return "region" if gesture.drawing_region else "point"

    def move(self, u, v, screen):
        fraction = self._fraction(u, v)
        if fraction is None:
            return
        changed = self._gesture().move(fraction, screen)
        if changed is not None:
            self.window._pointer_changed(changed)

    def release(self, u, v, screen):
        targets = getattr(self.window, "pointer_targets", None)
        fraction = self._fraction(u, v)
        if targets is None or fraction is None:
            self._gesture().cancel()
            return
        changed = self._gesture().release(targets, fraction, screen)
        if changed is not None:
            self.window._pointer_changed(changed)


def _sip_module():
    """The sip module of the PyQt binding in use; None for PySide (no ownership API used)."""
    package = QApplication.__module__.split(".")[0]
    if not package.startswith("PyQt"):
        return None
    try:
        return importlib.import_module(f"{package}.sip")
    except ImportError:
        return None


def defer_deletion(widget) -> bool:
    """Hand a garbage-collected top-level widget to Qt and delete it from the event loop.

    A window the program dropped without closing it stays on screen, owned by
    its Python wrapper in a reference cycle (gui <-> window), so the cyclic
    garbage collector deletes it whenever it happens to run: possibly inside
    one of the window's own paint events (matplotlib canvases and image views
    paint in Python, which allocates), which then go on painting a deleted
    widget and crash the process (``QPaintDevice: Cannot destroy paint device
    that is being painted``, ``Fatal Python error: Segmentation fault``).
    Called from ``__del__``: ownership goes to C++ (sip keeps the wrapper alive
    until then) and ``deleteLater`` deletes the widget outside any event
    handler. True when the deletion was deferred.
    """
    sip = _sip_module()
    try:
        if sip is None or sip.isdeleted(widget) or not sip.ispyowned(widget):
            return False
        if QApplication.instance() is None:
            return False  # no event loop to delete it later: deleted now, as before
        sip.transferto(widget, None)
        widget.deleteLater()
        return True
    except Exception:  # broad on purpose: called by the garbage collector, never raise there
        return False


def _format_pixel_value(value) -> str:
    if isinstance(value, tuple):
        return "(" + ", ".join(f"{v:.4g}" for v in value) + ")"
    return f"{value:.4g}"


def _set_window_icon(app) -> None:
    path = icon_path("png")
    if path:
        app.setWindowIcon(QIcon(path))


class InteractivePipeQT(InteractivePipeGUI):
    # click (< 3 px of movement) sets a PointControl, shift-drag draws a RegionControl
    pointer_gestures = True

    def init_app(self, threaded: bool = False, **kwargs):
        """`threaded=True` runs the pipeline in a worker thread (widgets stay
        live during slow runs, results are displayed when ready)."""
        if threaded and self.audio:
            # filters would drive the QMediaPlayer from the worker thread
            raise ValueError("threaded=True does not support audio=True: run the audio pipeline without threaded")
        quiet_offscreen_messages()  # snapshots / the command line build windows never shown
        if not QApplication.instance():
            self.app = QApplication(sys.argv)
        else:
            self.app = QApplication.instance()
        _set_window_icon(self.app)

        self.window = MainWindow(
            controls=self.controls,
            name=self.name,
            pipeline=self.pipeline,
            size=self.size,
            main_gui=self,
            **kwargs,
        )
        self.set_default_key_bindings()
        self.build_menu_bar()
        if threaded:
            self.window.start_threaded_runs()

        self.player = None
        if self.audio:
            # The player is created a little later (avoids PipeWire sync blocking at start-up):
            # until then the sound the first runs ask for is recorded, and replayed once it exists.
            self._pending_audio = None
            self._pending_playback = None
            audio = self.pipeline.framework_state.audio
            audio.accepts_signals = qt_audio_stream.QAudioSink is not None
            audio.load_audio = self._record_audio_request
            audio.play = partial(self._record_playback, "play")
            audio.pause = partial(self._record_playback, "pause")
            audio.stop = partial(self._record_playback, "stop")
            QTimer.singleShot(100, self.audio_player)

    def run(self) -> list:
        if not self.pipeline._PipelineCore__initialized_inputs:  # type: ignore[reportAttributeAccessIssue]
            raise RuntimeError("Did you forget to initialize the pipeline inputs?")
        self.window.refresh()
        if self.app is not None:
            self.app.exec()
        self.window.stop_threaded_runs()
        self.custom_end()
        results = self.pipeline.results
        if results is None:
            return []
        if isinstance(results, tuple):
            return list(results)
        return results  # type: ignore[reportReturnType]

    def build_menu_bar(self):
        """File / View / Pipeline / Help menus built from the actions registry.

        Entries show their key as shortcut text only (after a tab): real
        QAction shortcuts would fire twice with MainWindow.keyPressEvent.
        """
        self.menu_bar = QMenuBar(self.window)
        self.menu_actions: Dict[str, object] = {}
        for group, actions in self.actions_by_menu().items():
            menu = self.menu_bar.addMenu(group)
            if menu is None:
                raise RuntimeError(f"Cannot create the {group} menu")
            for action in actions:
                qt_action = menu.addAction(f"{action.label}\t{action.key.upper()}")
                if qt_action is None:
                    raise RuntimeError(f"Cannot create the {action.label} menu entry")
                qt_action.setToolTip(action.doc)
                qt_action.setStatusTip(action.doc)
                qt_action.triggered.connect(lambda _checked=False, act=action: self.trigger_menu_action(act))
                self.menu_actions[action.name] = qt_action
        self.window.layout().setMenuBar(self.menu_bar)  # pyright: ignore[reportOptionalMemberAccess]

    def trigger_menu_action(self, action: Action):
        """Run a menu entry, then give the keyboard focus back to the window."""
        self.run_action(action)
        self.window.setFocus()

    @staticmethod
    def _file_filter(extensions: List[str]) -> str:
        patterns = " ".join(f"*{ext}" for ext in extensions)
        return f"Supported files ({patterns});;All files (*)"

    def ask_path(self, title: str, save: bool, extensions: List[str], default_name: str) -> Optional[Path]:
        """Native Qt file dialog; None when cancelled."""
        dialog = QFileDialog.getSaveFileName if save else QFileDialog.getOpenFileName
        path, _selected_filter = dialog(self.window, title, default_name, self._file_filter(extensions))
        self.window.setFocus()
        if not path:
            return None
        return Path(path)

    def close(self):
        """close GUI"""
        if self.app is not None:
            self.app.quit()

    def reset_parameters(self):
        """reset sliders to default parameters and fit the images back to their cells"""
        super().reset_parameters()
        self.fit_view()
        for widget_idx, ctrl in self.window.ctrl.items():
            if isinstance(ctrl, TimeControl):
                # self.suspend_resume_timer(True)
                # self.time_playing = False
                self.start_time = None  # Reset the timer
            ctrl.value = ctrl.value_default
        self.window.reset_sliders()

    def add_controls(self, new_controls):
        """A ``Video`` input's timeline joins the window built before the inputs were given."""
        others = []
        for ctrl in new_controls:
            if isinstance(ctrl, TimelineControl):
                self.window.add_timeline(ctrl)
            else:
                others.append(ctrl)
        if others:
            logging.warning(f"controls added after the window was built are not shown: {[c.name for c in others]}")

    def on_parameters_loaded(self):
        """sync the widgets with the imported parameters"""
        # HeadlessPipeline.parameters (set by import_tuning) writes the loaded
        # values back into the connected controls; the widgets just need syncing.
        self.window.reset_sliders()

    def save_images(self):
        """save images to disk

        Saving runs the pipeline on the GUI thread: it takes the run lock (so
        it waits for an in-flight background run) and reads the controls
        first, so the saved images match the current parameters.
        """
        extensions = self._file_extensions(Image)

        def save_now(path: Path):
            self.pipeline.update_parameters_from_controls()
            self.pipeline.save(path, data_wrapper_fn=lambda im: Image(im), save_entire_buffer=True)

        def save(path: Path):
            path = Image.check_path(path, load=False, extensions=extensions)
            self.window.run_synchronously(lambda: save_now(path))

        default_name = f"{self._default_file_stem()}{extensions[0]}"
        self._with_path("Save images", True, extensions, default_name, save)

    def print_message(self, message_list: List[str]):
        print("\n".join(message_list))
        QMessageBox.about(self.window, self.name, "\n".join(message_list))

    # ---------------------------- VIEW (image viewer) ---------------------------------
    def fit_view(self):
        """fit the images to their cells"""
        self.window.set_view_mode("fit")
        self.window.reset_view()

    def actual_size_view(self):
        """show the images at their actual size (1:1)"""
        self.window.set_view_mode("1:1")

    def zoom_in(self):
        """zoom in (all image cells)"""
        self.window.zoom_in()

    def zoom_out(self):
        """zoom out (all image cells)"""
        self.window.zoom_out()

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

    def _record_audio_request(self, request):
        self._pending_audio = request

    def _record_playback(self, action):
        self._pending_playback = action

    def audio_player(self):
        self.player = QtAudioPlayer()
        audio = self.pipeline.framework_state.audio
        audio.set_audio = self.player.set_audio
        audio.load_audio = self.player.load
        audio.accepts_signals = self.player.accepts_signals
        audio.play = self.player.play
        audio.pause = self.player.pause
        audio.stop = self.player.stop
        if self.app is not None:
            self.app.aboutToQuit.connect(self.close_audio)
        if self._pending_audio is not None:
            self.player.load(self._pending_audio)
            if self._pending_playback is not None:
                getattr(self.player, self._pending_playback)()
        self._pending_audio = self._pending_playback = None

    def close_audio(self):
        """Stop the sound and its thread (window closed, application quitting)."""
        if self.player is not None:
            self.player.stop()
            self.player.close()


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
    # raw pipeline output at that pixel (None outside). Defaults to the status
    # line readout; replace it with your own callback, or None -> tooltip readout.
    on_pixel_hover: Optional[Callable[[int, int, int, int, Any], None]] = None
    ERROR_STYLE = "color: #d32f2f; font-weight: bold;"

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
        # tooltips (elided titles, control help) also when the window is not the active one
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips)

        # Track detached panel windows
        self.detached_windows = []
        # Set by QtPanelBuilder when a TimeControl widget is created
        self.timer: Optional[QTimer] = None
        # coalesced refresh (request_refresh) and in-window error display
        self._refresh_pending = False
        self._suppress_refresh_requests = False
        self.last_error: Optional[Exception] = None
        self._run_status = ""
        self.on_pixel_hover = self._status_pixel_hover
        # threaded runs (opt-in): a worker thread + a lock serializing every run
        self._run_lock = threading.Lock()
        self._run_seq = 0  # incremented by each run; stale worker results are dropped
        self._displayed_seq = 0
        self._runner: Optional[PipelineRunner] = None
        self._figure_boxes: Dict[Any, Any] = {}  # (row, col) -> view size, read by the worker
        self._figure_sources: Dict[Any, Any] = {}  # (row, col) -> Figure displayed there
        self._figure_ratio = 1.0
        # (outputs, output_styles) captured by the worker with the run being
        # displayed: the next run may already be changing the live ones
        self._display_layout: Optional[tuple] = None
        # window sizing: (width, height, time, size before, retry) last asked by _fit_window_to_images;
        # usable size learned when the window manager shrank one (None: it never did)
        self._resize_request: Optional[tuple] = None
        self._granted_limit: Optional[tuple] = None
        self._retry_size: Optional[tuple] = None

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
        # the controls below spread over columns when the images take the room,
        # and scroll in their own area when even that is not enough;
        # bottom_panels_layout is the first column
        bottom_content = ControlsContent()
        self.bottom_columns_layout = QHBoxLayout()
        self.bottom_columns_layout.setContentsMargins(0, 0, 0, 0)
        self.bottom_columns_layout.setSpacing(CONTROL_COLUMN_GAP)
        bottom_content.setLayout(self.bottom_columns_layout)
        self.bottom_columns_layout.addLayout(self.bottom_panels_layout)
        self.bottom_panels_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._bottom_items: List[QWidget] = []  # in display order
        self._extra_columns: List[QVBoxLayout] = []
        self.bottom_scroll = ControlsScrollArea(bottom_content)
        # deferred work owned by the window (a bare QTimer.singleShot can fire on a dead window)
        self._columns_timer = self._child_timer(self._columns_for_window_size)
        self._retry_timer = self._child_timer(self._retry_resize)
        main_layout.addWidget(self.bottom_scroll)

        # Status line: last run timings / errors, pixel readout on hover
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.status_label.setStyleSheet("font-family: monospace; font-size: 11px; color: gray;")
        main_layout.addWidget(self.status_label)

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
                self._bottom_items.append(row_widget)

        for panel in panels_by_position["bottom"]:
            panel_widget = self._build_panel_widget(panel, control_factory)
            self.bottom_panels_layout.addWidget(panel_widget)
            self._bottom_items.append(panel_widget)

        self.bottom_scroll.setVisible(self.bottom_panels_layout.count() > 0)

        # Create detached windows for detached panels (position is ignored for detached)
        for panel in detached_panels:
            detached_window = DetachedPanelWindow(panel, self, control_factory)
            self.detached_windows.append(detached_window)

    def add_timeline(self, ctrl: TimelineControl) -> None:
        """Full-width timeline of the ``Video`` inputs, at the bottom of the window (above the status line)."""
        from interactive_pipe.graphical.qt_timeline import TimelineWidget

        if ctrl.name in self.widget_list:
            return
        widget = TimelineWidget(self, ctrl)
        self.ctrl[ctrl.name] = ctrl
        self.widget_list[ctrl.name] = widget  # reset_sliders -> widget.reset()
        main_layout = self.layout()
        main_layout.insertWidget(main_layout.indexOf(self.status_label), widget)  # type: ignore[union-attr]
        self.timeline_widget = widget
        if self.main_gui is not None:
            self.main_gui.bind_timeline_keys(widget.play_pause, widget.step)

    def update_label(self, idx):
        # pass
        val = self.ctrl[idx].value
        val_to_print = format_value(val)
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
        self.request_refresh()

    def key_update_parameter(self, idx, down):
        """Required implementation for keyboard sliders update"""
        if down:
            self.ctrl[idx].on_key_down()
        else:
            self.ctrl[idx].on_key_up()
        # self.update_label(idx)
        self.request_refresh()

    def request_refresh(self):
        """Schedule one refresh on the next event loop pass.

        Every widget event goes through here: a slider drag emitting many
        values while the pipeline runs yields a single run with the latest
        values instead of one queued run per tick.
        """
        if self._suppress_refresh_requests:
            return  # reset_sliders runs once after syncing every widget
        if self._runner is not None:
            self._runner.request()
            self.set_status(f"{self._run_status} · running…" if self._run_status else "running…")
            return
        if self._refresh_pending:
            return
        self._refresh_pending = True
        QTimer.singleShot(0, self._flush_refresh)

    # --- threaded runs (InteractivePipeQT(threaded=True)) ---
    @property
    def threaded(self) -> bool:
        return self._runner is not None

    def start_threaded_runs(self):
        """Run widget-triggered refreshes in a worker thread (latest wins)."""
        if self._runner is not None:
            return
        self._runner = PipelineRunner(self._run_pipeline_in_worker, self._run_lock)
        self._runner.run_finished.connect(self._on_threaded_run_finished)
        self._runner.start()

    def stop_threaded_runs(self):
        """Stop the worker thread (lets the current run finish). Idempotent."""
        runner, self._runner = self._runner, None
        if runner is not None:
            runner.stop()

    def _on_threaded_run_finished(self, result):
        seq, out, error, report, display_layout = result
        if seq < self._displayed_seq:
            return  # a synchronous refresh already displayed newer results
        self._display_layout = display_layout
        try:
            self._display_run(seq, out, error, report)
        finally:
            self._display_layout = None
        if self._runner is not None and self._runner.busy:
            self.set_status(f"{self._run_status} · running…")

    def _flush_refresh(self):
        try:
            if not self._refresh_pending:
                return  # a synchronous refresh() already ran in between
        except RuntimeError:  # the window was destroyed before the timer fired
            return
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
        view.pointer_handler = _CellPointerHandler(self, view, row, col)
        view.resized_callback = lambda: self._refit_figure(view, row, col)
        self.image_grid_layout.addWidget(view, 2 * row + 1, col)
        return view

    def set_status(self, text: str):
        """Show `text` in the status line at the bottom of the window."""
        self.status_label.setText(text)

    def _status_pixel_hover(self, row, col, x, y, value):
        """Default on_pixel_hover: pixel readout appended to the status line."""
        if value is None:
            self.set_status(self._run_status)
        else:
            separator = " · " if self._run_status else ""
            where = self._pixel_location(row, col, x, y)
            self.set_status(f"{self._run_status}{separator}{where} = {_format_pixel_value(value)}")

    def _pixel_location(self, row, col, x, y) -> str:
        """``(x, y)`` data pixel, preceded by its extent coordinates when the
        heatmap has ``layout.style(extent=...)``."""
        try:
            readout = getattr(self.image_canvas[row][col]["image"], "readout", None)  # type: ignore[index]
        except (TypeError, IndexError, KeyError):
            readout = None
        if readout is not None and getattr(readout, "extent", None) is not None:
            data_x, data_y = readout.data_coordinates(x, y)
            return f"x={data_x:.4g}, y={data_y:.4g} ({x}, {y})"
        return f"({x}, {y})"

    def _status_title_hover(self, title: Optional[str]):
        """Full text of an elided output title appended to the status line while it is hovered."""
        if title is None:
            self.set_status(self._run_status)
        else:
            separator = " · " if self._run_status else ""
            self.set_status(f"{self._run_status}{separator}{' — '.join(title.splitlines())}")

    def _on_view_hover(self, view, row, col, x, y, value):
        if self.on_pixel_hover is not None:
            self.on_pixel_hover(row, col, x, y, value)
        else:
            if value is None:
                view.setToolTip("")
                return
            view.setToolTip(f"{self._pixel_location(row, col, x, y)}: {_format_pixel_value(value)}")

    def _expand_image_grid(self):
        """Give the image grid all the spare room (it is wrapped in centering
        stretches): image views then fit the window as the user resizes it."""
        child = self.image_grid_layout
        parent = child.parent()
        while isinstance(parent, (QHBoxLayout, QVBoxLayout)):
            parent.setStretchFactor(child, 1)
            child, parent = parent, parent.parent()

    def set_view_mode(self, mode: str):
        """ "fit" (default) or "1:1" for every image cell (zoom/pan reset).

        1:1 grows the window (up to the screen size) so the images show whole at
        their native size, the controls below get the room left and scroll; the
        window outgrows the screen only when the images alone do not fit.
        Going back to fit restores the previous size.
        """
        sync = self._view_sync()
        was_absolute = sync.absolute
        sync.set_mode(mode)
        if sync.absolute and not was_absolute:
            self._size_before_actual = (self.width(), self.height())
            self._fit_window_to_images()
        elif not sync.absolute:
            previous = getattr(self, "_size_before_actual", None)
            self._size_before_actual = None
            if previous is not None and not (self.full_screen_flag or self.isMaximized() or self.isFullScreen()):
                self._resize_request = None  # deliberate: not an answer to the 1:1 growth
                self.resize(*previous)

    def zoom_in(self):
        self._sync_zoom(True)

    def zoom_out(self):
        self._sync_zoom(False)

    def _sync_zoom(self, zoom_in: bool):
        # zoom around the center of a view showing an image: the state is shared anyway
        views = [view for view in self._view_sync().views if view.has_image()]
        if not views:
            return
        views[0].zoom_in() if zoom_in else views[0].zoom_out()

    def reset_view(self):
        self._view_sync().reset()

    def refresh_display(self, _out) -> None:
        # Keep the raw (float) outputs so the views report true pixel values;
        # convert_image only produces the 8-bit display copy.
        self._raw_outputs = _normalize_output_grid(_out)
        figures = _figure_positions(self._raw_outputs)
        if figures or self._runner is None:  # worker runs: recorded by the worker (figures already rasterised)
            self._figure_sources = figures
        super().refresh_display(_out)
        self._update_pointer_targets()

    # --- point / region controls: gestures on the image views, overlay ---
    def _update_pointer_targets(self) -> None:
        controls = pointer_controls(getattr(self.pipeline, "controls", None))
        if not controls:
            self.pointer_targets = None
            return
        if self._display_layout is not None:
            names = self._display_layout[0]
        else:
            names = self.pipeline.outputs  # type: ignore[reportOptionalMemberAccess]
        styles = {}
        for row, cells in enumerate(self.image_canvas or []):
            for col, cell in enumerate(cells):
                if cell is not None:
                    try:
                        styles[(row, col)] = self.get_current_style(row, col)
                    except (IndexError, KeyError, TypeError, RuntimeError):
                        pass
        self.pointer_targets = PointerTargets(controls, names, self._raw_outputs, styles)
        self._update_pointer_overlays()

    def _pointer_data_size(self, view: ImageView, row: int, col: int):
        targets = getattr(self, "pointer_targets", None)
        if targets is None or not view.has_image():
            return None
        width, height = view.image_size()
        return targets.data_size((row, col), (height, width))

    def _update_pointer_overlays(self) -> None:
        targets = getattr(self, "pointer_targets", None)
        for row, cells in enumerate(self.image_canvas or []):
            for col, cell in enumerate(cells):
                if cell is None or not isinstance(cell.get("image"), ImageView):
                    continue
                view = cell["image"]
                size = self._pointer_data_size(view, row, col)
                if targets is None or size is None or cell.get("kind") != "image":
                    view.set_overlay([])
                else:
                    view.set_overlay(overlay_items(targets, (row, col), size))

    def _pointer_changed(self, ctrl) -> None:
        """A gesture set a new value: move the overlay now, run the pipeline (coalesced)."""
        self._update_pointer_overlays()
        self.update_parameter(ctrl.name, ctrl.value)

    # --- matplotlib figure outputs: drawn at the size of their cell ---
    def figure_box(self, row, col):
        """Size of the view of cell (row, col): a figure output is drawn at
        that size, its text the size of a Curve's (None before layout)."""
        return self._figure_boxes.get((row, col))

    def figure_pixel_ratio(self) -> float:
        return self._figure_ratio  # read by the worker: cached on the GUI thread

    def _refit_figure(self, view, row, col) -> None:
        """The view of (row, col) was resized: draw its figure output again at the new size."""
        self._figure_boxes[(row, col)] = view.logical_size()
        self._figure_ratio = view.pixel_ratio()
        figure = self._figure_sources.get((row, col))
        cell = (self.image_canvas or [[]])[row][col] if row < len(self.image_canvas or []) else None
        if figure is None or cell is None or cell.get("image") is not view or cell.get("kind") != "image":
            return
        dpi = (self.get_current_style(row, col) or {}).get("dpi")
        shown = self.run_synchronously(
            lambda: rasterize_figure(figure, dpi, view.logical_size(), self.figure_pixel_ratio())
        )
        view.set_image(numpy_to_pixmap(self.convert_image(shown)), shown)

    def _raw_output(self, row, col) -> Any:
        grid = getattr(self, "_raw_outputs", None)
        try:
            return grid[row][col] if grid is not None else None
        except (IndexError, TypeError):
            return None

    def add_image_placeholder(self, row, col):
        ax_placeholder = None
        # long titles get "…"; hovering shows the full title in a tooltip and the status line
        text_label = ElidedLabel(f"{row} {col}", on_hover=self._status_title_hover)
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
                discard_widget(widget)
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
            discard_widget(cell["image"])
            cell["plot_object"] = None
            cell["ax_placeholder"] = None
            cell["image"] = self._new_image_view(row, col)
        # image <-> text share the same ImageView (setText/set_image replace each other)

    def _deferred_fit_window(self):
        try:
            self._fit_window_pending = False
            self._fit_window_to_images()
        except RuntimeError:  # the window was destroyed before the timer fired
            pass

    def _screen_room(self) -> Optional[tuple]:
        """(width, height) the window can take on its screen (client area), None without screen."""
        screen = self.screen() if hasattr(self, "screen") else None
        if screen is None:
            return None
        available = screen.availableGeometry()
        # the size set is the client area: leave room for the title bar and borders
        frame, client = self.frameGeometry(), self.geometry()
        deco_w, deco_h = max(0, frame.width() - client.width()), max(0, frame.height() - client.height())
        width, height = available.width() - deco_w, available.height() - deco_h
        if self._granted_limit is not None:
            width, height = min(width, self._granted_limit[0]), min(height, self._granted_limit[1])
        return width, height

    def _relayout_now(self):
        layout = self.layout()
        if layout is not None:
            layout.invalidate()  # drop cached size hints (freshly filled views, new columns)
            layout.activate()

    def _set_control_columns(self, count: int) -> bool:
        """Spread the bottom controls over `count` columns (in order, balanced
        heights); False when they already are."""
        items = self._bottom_items
        heights = [w.sizeHint().expandedTo(w.minimumSizeHint()).height() for w in items]
        columns = split_into_columns(heights, count, self.bottom_panels_layout.spacing()) if items else []
        current = [layout_widgets(layout) for layout in [self.bottom_panels_layout, *self._extra_columns]]
        wanted = [[items[i] for i in column] for column in columns]
        if [c for c in current if c] == wanted:
            return False
        for layout in [self.bottom_panels_layout, *self._extra_columns]:
            for widget in layout_widgets(layout):
                layout.removeWidget(widget)
        while len(self._extra_columns) > max(0, len(wanted) - 1):
            extra = self._extra_columns.pop()
            self.bottom_columns_layout.removeItem(extra)
            extra.deleteLater()
        while len(self._extra_columns) < len(wanted) - 1:
            extra = QVBoxLayout()
            extra.setSpacing(self.bottom_panels_layout.spacing())
            extra.setAlignment(Qt.AlignmentFlag.AlignTop)
            self.bottom_columns_layout.addLayout(extra)
            self._extra_columns.append(extra)
        for layout, widgets in zip([self.bottom_panels_layout, *self._extra_columns], wanted):
            for widget in widgets:
                layout.addWidget(widget)
        return True

    def _update_control_columns(self, width: int, height: int) -> bool:
        """Fewest columns of controls that fit a `width` x `height` window
        next to the images at their preferred size (native at 1:1); as many as
        the width holds when the controls do not fit (they scroll). True when
        the columns changed."""
        items = self._bottom_items
        if len(items) < 2 or not self.bottom_scroll.isVisibleTo(self):
            return False
        widths = [w.sizeHint().expandedTo(w.minimumSizeHint()).width() for w in items]
        heights = [w.sizeHint().expandedTo(w.minimumSizeHint()).height() for w in items]
        bar = self.bottom_scroll.verticalScrollBar()
        bar_width = bar.sizeHint().width() if bar is not None else 0
        # the window can always shrink to a single column (fewer columns follow)
        self.bottom_scroll.minimum_width = max(widths) + bar_width
        margins = self.layout().contentsMargins()  # type: ignore[union-attr]
        width_room = width - margins.left() - margins.right() - bar_width
        others = self.sizeHint().height() - self.bottom_scroll.sizeHint().height()
        count = choose_column_count(
            heights,
            widths,
            width_room,
            height - others,
            spacing=self.bottom_panels_layout.spacing(),
            column_gap=CONTROL_COLUMN_GAP,
        )
        changed = self._set_control_columns(count)
        if changed:
            self.bottom_scroll.updateGeometry()
            self._relayout_now()
        return changed

    def _child_timer(self, slot) -> QTimer:
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(0)
        timer.timeout.connect(slot)
        return timer

    def _columns_for_window_size(self):
        if self.isVisible():
            self._update_control_columns(self.width(), self.height())

    def _fit_window_to_images(self):
        """Grow the window once so new image cells get their preferred size
        (views can shrink, so Qt no longer grows the window by itself).

        The controls first spread over the columns that let them fit the
        screen next to the images (the window grows wider for them). The size
        is clamped to the screen, but never below the minimum size of the
        layout (at 1:1 the native size of the images)."""
        if self.full_screen_flag or self.isMaximized() or self.isFullScreen():
            return
        self._relayout_now()
        room = self._screen_room()
        if room is not None:
            self._update_control_columns(*room)
        hint = self.sizeHint()
        width, height = max(self.width(), hint.width()), max(self.height(), hint.height())
        if room is not None:
            width, height = min(width, room[0]), min(height, room[1])
        minimum = self.minimumSizeHint()  # an explicit `size` lifts the window minimum off the layout's
        width, height = max(width, minimum.width()), max(height, minimum.height())
        if (width, height) != (self.width(), self.height()):
            self._request_resize(width, height)

    def _request_resize(self, width: int, height: int, retry: bool = True):
        self._resize_request = (width, height, time.monotonic(), (self.width(), self.height()), retry)
        self.resize(width, height)

    def resizeEvent(self, event):  # noqa: N802 - Qt API
        # On Wayland the available screen geometry includes the panels, but the
        # compositor shrinks a window that would not fit (after Qt echoed the
        # requested size): remember what it granted as the usable size. A size
        # back at (or below) the one before the request is a stale configure,
        # not a limit: ask again, once.
        super().resizeEvent(event)
        self._columns_timer.start()  # the columns of controls follow the window size
        size = (event.size().width(), event.size().height())
        request = self._resize_request
        if request is None or time.monotonic() - request[2] > RESIZE_ANSWER_DELAY:
            self._resize_request = None
            return
        if size == request[:2]:
            return  # Qt's echo of the request, the compositor may still shrink it
        self._resize_request = None
        if not (size[0] <= request[0] and size[1] <= request[1]):
            return
        before, retry = request[3], request[4]
        grew = [size[i] > before[i] for i in (0, 1) if size[i] < request[i]]  # the shrunk dimensions
        if grew and all(grew):
            limit = self._granted_limit or (NO_LIMIT, NO_LIMIT)
            self._granted_limit = (
                size[0] if size[0] < request[0] else limit[0],
                size[1] if size[1] < request[1] else limit[1],
            )
        elif retry:
            self._retry_size = (request[0], request[1])
            self._retry_timer.start()

    def _retry_resize(self):
        size, self._retry_size = self._retry_size, None
        if size is not None and not (self.full_screen_flag or self.isMaximized() or self.isFullScreen()):
            self._request_resize(*size, retry=False)

    def _fit_window_once(self, cell) -> None:
        """Grow the window for a cell that just received its first content."""
        if cell.pop("fit_window", False):
            # deferred: views added to a shown window only become visible
            # (and count in the layout size hint) on the next event loop pass
            if not getattr(self, "_fit_window_pending", False):
                self._fit_window_pending = True
                QTimer.singleShot(0, self._deferred_fit_window)

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
            raw = display_data(self._raw_output(row, col))  # Image -> its array
            # heatmap with a colorbar: report the scalar under the cursor, in data pixels
            readout = heatmap_geometry(raw, self.get_current_style(row, col))
            if readout is None and (not isinstance(raw, np.ndarray) or raw.shape[:2] != shown.shape[:2]):
                raw = shown
            cell["image"].set_image(numpy_to_pixmap(shown), raw, readout=readout)
            self._fit_window_once(cell)
        elif MPL_SUPPORT and FigureCanvas is not None and isinstance(image_array_original, Curve):
            update_curve_cell(cell, self.image_grid_layout, row, col, image_array_original)
            self._fit_window_once(cell)  # a window holding only plots also gives room to its controls
        elif MPL_SUPPORT and FigureCanvas is not None and isinstance(image_array_original, Table):
            update_table_cell(cell, self.image_grid_layout, row, col, image_array_original)
            self._fit_window_once(cell)
        elif isinstance(image_array_original, str):
            # keep "fit_window": the window grows when an image shows up later
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
        """Run the pipeline now and display the results.

        A filter raising (FilterError) does not escape: the error is shown in
        the window (cells + status line) and the next good run restores it.
        """
        self._refresh_pending = False
        if self.pipeline is None:
            return
        with self._run_lock:  # waits for a background run in threaded mode
            result = self._run_pipeline()
        self._display_run(*result)

    def run_synchronously(self, fn: Callable[[], Any]) -> Any:
        """Call `fn` on this thread while no pipeline run is in progress.

        Use it for anything running the pipeline from the GUI thread (saving
        images...): in threaded mode it waits for the in-flight background run.
        """
        with self._run_lock:
            return fn()

    def _run_pipeline(self):
        """Run the pipeline (caller holds _run_lock): (seq, out, error, report)."""
        self._run_seq += 1
        seq = self._run_seq
        out, error = None, None
        try:
            out = self.pipeline.run()  # type: ignore[reportOptionalMemberAccess]
        except FilterError as exc:
            error = exc
        return seq, out, error, self.pipeline.last_run_report  # type: ignore[reportOptionalMemberAccess]

    def _run_pipeline_in_worker(self):
        """_run_pipeline for the worker thread: any other exception becomes a
        failed result too, so the GUI thread shows it instead of "running…"."""
        try:
            result = self._run_pipeline()
        except Exception as exc:  # broad on purpose: report it in the window
            logging.exception("Background pipeline run failed")
            result = self._run_seq, None, exc, None
        layout = self._snapshot_layout()
        seq, out, error, report = result
        if out is not None:
            # draw matplotlib figures here, under the run lock: the next run may
            # reuse (clear and redraw) the same Figure while the GUI thread displays
            self._figure_sources = _figure_positions(_normalize_output_grid(out))
            out = _rasterize_figures(out, layout, self._figure_boxes, self.figure_pixel_ratio())
        return (seq, out, error, report, layout)

    def _snapshot_layout(self) -> tuple:
        """Copy of the output names grid and styles (taken in the worker)."""
        outputs = self.pipeline.outputs  # type: ignore[reportOptionalMemberAccess]
        if outputs is not None:
            outputs = [list(row) if isinstance(row, (list, tuple)) else row for row in outputs]
        styles = self.pipeline.framework_state.output_styles  # type: ignore[reportOptionalMemberAccess]
        return outputs, {name: dict(style) for name, style in styles.items()}

    def get_current_style(self, row, col):
        if self._display_layout is None:
            return super().get_current_style(row, col)
        outputs, styles = self._display_layout
        name = outputs[row][col]
        return self.resolve_style(name, styles, row, col)

    def error_cell_positions(self, error):
        if self._display_layout is None:
            return super().error_cell_positions(error)
        # same as InteractivePipeWindow.error_cell_positions, on the snapshot
        outputs = self._display_layout[0]
        if self.image_canvas is None and outputs:
            self.set_image_canvas(outputs)
        positions = [
            (row, col)
            for row, cells in enumerate(self.image_canvas or [])
            for col, cell in enumerate(cells)
            if cell is not None
        ]
        failing_outputs = set()
        for filt in getattr(self.pipeline, "filters", None) or []:
            if filt.name == error.filter_name:
                failing_outputs = set(filt.outputs or [])
        matching = []
        for row, col in positions:
            try:
                name = outputs[row][col]
            except (IndexError, TypeError):
                continue
            if name in failing_outputs:
                matching.append((row, col))
        return matching or positions[:1]

    def _display_run(self, seq, out, error: Optional[Exception], report):
        self._displayed_seq = seq
        if isinstance(error, FilterError):
            self.show_error(error)
            return
        if error is not None:  # raised outside the filters (threaded runs only)
            self.last_error = error
            self._run_status = "error"
            self.set_status(f"error: {type(error).__name__}: {error}")
            return
        self._clear_error_style()
        self.last_error = None
        self.refresh_display(out)
        self._run_status = format_run_status(report)
        self.set_status(self._run_status)

    def show_error(self, error: FilterError):
        """Display a pipeline error in the window instead of raising."""
        self.last_error = error
        self.report_error(error)  # on the console too, once
        original = error.original_error
        message = format_error_message(error)
        for row, col in self.error_cell_positions(error):
            cell = self.image_canvas[row][col]  # type: ignore[index]
            if cell.get("kind") in ("curve", "table"):
                self._reset_cell_widget(cell, cell["row"], cell["col"], "text")
            cell["kind"] = "text"
            # keep "fit_window": the window grows once the error is fixed
            cell["image"].setText(message)
            cell["image"].setWordWrap(True)
            cell["image"].setStyleSheet(self.ERROR_STYLE)
            cell["error"] = True
        self._run_status = f"error in {error.filter_name}"
        self.set_status(f"{self._run_status}: {type(original).__name__}: {original}")

    def _clear_error_style(self):
        for row in self.image_canvas or []:
            for cell in row:
                if cell is not None and cell.pop("error", False):
                    cell["image"].setStyleSheet("")
                    cell["image"].setWordWrap(False)

    def reset_sliders(self):
        """Sync every widget with its control value, then run once.

        The widgets emit a value change each; those refresh requests are
        dropped: a single run follows (in the worker when threaded, so a reset
        or an import does not block the GUI thread on the run lock).
        """
        self._suppress_refresh_requests = True
        try:
            for widget_idx, ctrl in self.ctrl.items():
                if widget_idx in self.widget_list.keys():
                    self.widget_list[widget_idx].reset()
                self.update_label(widget_idx)
        finally:
            self._suppress_refresh_requests = False
        if self.threaded:
            self.request_refresh()
        else:
            self.refresh()

    def __del__(self):
        # garbage collected while possibly still shown: never delete it mid-paint (see defer_deletion)
        for detached_window in getattr(self, "detached_windows", []):
            defer_deletion(detached_window)
        defer_deletion(self)

    def closeEvent(self, event):
        """Handle main window close event - close all detached windows."""
        self.stop_threaded_runs()
        main_gui = getattr(self, "main_gui", None)
        if main_gui is not None and hasattr(main_gui, "close_audio"):
            main_gui.close_audio()
        # Close all detached panel windows
        for detached_window in self.detached_windows:
            detached_window.close()
        self.detached_windows.clear()
        event.accept()
