import logging
import sys
from typing import List, Optional

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

# Re-exported for backward compatibility (they lived in this module until 0.9.x)
from interactive_pipe.graphical.qt_widgets import CollapsibleBox, DetachedPanelWindow  # noqa: F401
from interactive_pipe.graphical.window import InteractivePipeWindow
from interactive_pipe.headless.control import Control, TimeControl
from interactive_pipe.headless.keyboard import KeyboardControl
from interactive_pipe.headless.panel import Panel
from interactive_pipe.headless.pipeline import HeadlessPipeline


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
        self.pipeline.global_params["__pipeline"] = self.pipeline
        self.set_default_key_bindings()

        if self.audio:
            # Set up placeholder functions so pipeline can run before audio is ready
            self.pipeline.global_params["__set_audio"] = lambda x: None
            self.pipeline.global_params["__play"] = lambda: None
            self.pipeline.global_params["__pause"] = lambda: None
            self.pipeline.global_params["__stop"] = lambda: None
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
        super().load_parameters()
        for widget_idx, widget in self.window.ctrl.items():
            matched = False
            for filtname, params in self.pipeline.parameters.items():
                for param_name in params.keys():
                    if param_name == widget.parameter_name_to_connect:
                        logging.debug(
                            f"MATCH & update {filtname} {widget_idx} with "
                            f"{self.pipeline.parameters[filtname][param_name]}"
                        )
                        self.window.ctrl[widget_idx].update(self.pipeline.parameters[filtname][param_name])
                        matched = True
            if not matched:
                raise ValueError(
                    f"could not match widget {widget_idx} with parameter to connect {widget.parameter_name_to_connect}"
                )
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
            window_size = self.window.size
            if window_size is not None and isinstance(window_size, str) and "full" in window_size.lower():
                # Special case where the window naturally goes to fullscreen since user defined it...
                # Force to go back to normal
                self.window.showNormal()
            else:  # Go back to normal size
                self.window.update_window()

    # ---------------------------- AUDIO FEATURE ----------------------------------------

    def audio_player(self):
        self.player = QtAudioPlayer()
        self.pipeline.global_params["__player"] = self.player.media_player
        self.pipeline.global_params["__set_audio"] = self.player.set_audio
        self.pipeline.global_params["__play"] = self.player.play
        self.pipeline.global_params["__pause"] = self.player.pause
        self.pipeline.global_params["__stop"] = self.player.stop


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
        self.pipeline.global_params["__window"] = self
        self.setWindowTitle(self.name)

        # Track detached panel windows
        self.detached_windows = []

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
        self.size = size
        self.full_screen_flag = False

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.show()

    @property
    def size(self):
        return self._size

    @size.setter
    def size(self, _size):
        if isinstance(_size, str):
            if "full" not in _size.lower() and "max" not in _size.lower():
                raise ValueError(f"size={_size} can only be among (full, fullscreen, maximized, max, maximum)")
        self._size = _size
        self.update_window()

    def update_window(self):
        self.full_screen_flag = False
        if self.size is None:
            self.showNormal()
            return
        if isinstance(self.size, str):
            if "max" in self.size.lower():
                self.maximize_screen()
            if "full" in self.size.lower():
                self.full_screen()
        else:
            self.showNormal()
            if isinstance(self.size, int):
                self.setMinimumWidth(self.size)
            elif isinstance(self.size, (tuple, list)):
                self.setMinimumWidth(self.size[0])
                self.setMinimumHeight(self.size[1])

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
        """Build widget for an element (Panel or Control).

        Args:
            element: Can be a Panel or Control instance
            control_factory: Factory for creating control widgets

        Returns:
            QWidget or None if element should be skipped
        """
        if isinstance(element, Panel):
            return self._build_panel_widget(element, control_factory)
        elif isinstance(element, Control):
            return self._create_control_widget(element, control_factory)
        return None

    def _build_panel_widget(self, panel: Panel, control_factory: ControlFactory) -> QWidget:
        """Recursively build Qt widget for a Panel.

        Args:
            panel: The Panel to build
            control_factory: Factory for creating control widgets

        Returns:
            QWidget containing the panel's content (CollapsibleBox or QGroupBox)
        """
        # Determine layout based on elements structure
        if panel.elements and isinstance(panel.elements[0], list):
            # Grid layout: list of lists
            layout = QGridLayout()
            for row_idx, row in enumerate(panel.elements):  # type: ignore[reportArgumentType]
                if isinstance(row, list):
                    for col_idx, element in enumerate(row):
                        widget = self._build_element_widget(element, control_factory)
                        if widget is not None:
                            layout.addWidget(widget, row_idx, col_idx)
        elif panel.elements:
            # Vertical layout: flat list
            layout = QVBoxLayout()
            layout.setSpacing(8)  # Nice spacing between controls
            for element in panel.elements:
                widget = self._build_element_widget(element, control_factory)
                if widget is not None:
                    layout.addWidget(widget)
        else:
            # No child elements, just a simple vertical layout for controls
            layout = QVBoxLayout()
            layout.setSpacing(8)  # Nice spacing between controls

        # Add controls assigned directly to this panel
        for ctrl in panel._controls:
            widget = self._create_control_widget(ctrl, control_factory)
            if widget is not None:
                layout.addWidget(widget)

        # Add stretch at the end to push all controls to the top
        # This creates a beautiful, balanced layout with controls at the top
        if isinstance(layout, QVBoxLayout):
            layout.addStretch()  # type: ignore[reportAttributeAccessIssue]

        # Create the panel widget (collapsible or regular)
        if panel.collapsible:
            # Use modern CollapsibleBox
            panel_widget = CollapsibleBox(title=panel.name or "", collapsed=panel.collapsed)
            panel_widget.set_layout(layout)
        else:
            # Use regular QGroupBox
            panel_widget = QGroupBox(panel.name or "")
            # Set nice margins for balanced appearance
            if isinstance(layout, QVBoxLayout):
                layout.setContentsMargins(12, 12, 12, 12)
            panel_widget.setLayout(layout)

        return panel_widget

    def _create_control_widget(self, ctrl: Control, control_factory: ControlFactory) -> Optional[QWidget]:
        """Helper method to create a single control widget with labels.
        Returns the row container widget or None if control should be skipped."""
        slider_name = ctrl.name

        if isinstance(ctrl, KeyboardControl):
            if self.main_gui is not None:
                self.main_gui.bind_keyboard_slider(ctrl, self.key_update_parameter)  # type: ignore[reportOptionalMemberAccess]
            return None
        elif isinstance(ctrl, TimeControl):
            self.timer = QTimer(self)

            def suspend_resume_timer(suspend: bool):
                if suspend:
                    logging.debug("Suspend")
                    self.timer.stop()
                else:
                    logging.debug("Resume")
                    self.timer.start()

            if self.main_gui is not None:
                self.main_gui.suspend_resume_timer = suspend_resume_timer  # type: ignore[reportOptionalMemberAccess]
                plugged_func = self.main_gui.plug_timer_control(ctrl, self.update_parameter, suspend_resume_timer)  # type: ignore[reportOptionalMemberAccess]
            else:

                def plugged_func():
                    pass

            self.timer.timeout.connect(plugged_func)
            self.timer.start(ctrl.update_interval_ms)
            return None
        elif isinstance(ctrl, Control):
            slider_instance = control_factory.create_control(ctrl, self.update_parameter)
            # Skip controls that return None (e.g., single-value controls)
            if slider_instance is None:
                return None
            if ctrl._type is str and ctrl.icons is not None:
                if ctrl.filter_to_connect is not None:
                    ctrl.filter_to_connect.cache = False  # type: ignore[reportOptionalMemberAccess]
                    ctrl.filter_to_connect.cache_mem = None  # type: ignore[reportOptionalMemberAccess]
                # Disable cache for dropdown menu with icons!
                # Allows clicking on the same item multiple times
            slider_or_layout = slider_instance.create()
            self.widget_list[slider_name] = slider_instance

            slider_layout = QHBoxLayout()
            slider_layout.setSpacing(8)  # Nice spacing between label, slider, and value

            if isinstance(slider_or_layout, QWidget):
                # Balanced label width that works well in both panels and bottom area
                label_fixed_width = 150
                label = QLabel("", self)
                label.setMinimumWidth(label_fixed_width)
                self.name_label[slider_name] = label
                slider_layout.addWidget(self.name_label[slider_name])
            if isinstance(slider_or_layout, QWidget):
                # If it's a QWidget, add it directly to the layout
                # Set minimum width to prevent slider from shrinking in narrow panels
                slider_or_layout.setMinimumWidth(150)
                # Add with stretch factor 1 so slider expands to fill available space
                slider_layout.addWidget(slider_or_layout, 1)
            elif isinstance(slider_or_layout, QHBoxLayout):
                slider_or_layout.setContentsMargins(0, 0, 0, 0)
                # If it's a QHBoxLayout, embed it in a QWidget first
                container_widget = QWidget()
                container_widget.setLayout(slider_or_layout)
                # Set minimum width to prevent shrinking in narrow panels
                container_widget.setMinimumWidth(150)
                slider_layout.addWidget(container_widget, 1)
            else:
                logging.warning(f"Unhandled type for slider: {type(slider_or_layout)}")
                return None
            if isinstance(slider_or_layout, QWidget):
                result_fixed_width = 90
                label = QLabel("", self)
                label.setMinimumWidth(result_fixed_width)
                self.result_label[slider_name] = label
                slider_layout.addWidget(self.result_label[slider_name])

            # Create a container widget for the entire row
            row_container_widget = QWidget()
            row_container_widget.setLayout(slider_layout)
            row_container_widget.setContentsMargins(0, 0, 0, 0)

            self.update_label(slider_name)
            return row_container_widget
        return None

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
        """Required implementation for graphical controllers update"""
        if self.ctrl[idx]._type is str:
            if self.ctrl[idx].value_range is None:
                self.ctrl[idx].update(value)
            else:
                self.ctrl[idx].update(self.ctrl[idx].value_range[value])
        elif self.ctrl[idx]._type is bool:
            self.ctrl[idx].update(bool(value))
        elif self.ctrl[idx]._type is float:
            if isinstance(self.ctrl[idx], TimeControl):
                self.ctrl[idx].update(value)
            else:
                self.ctrl[idx].update(self.ctrl[idx].convert_int_to_value(value))
        elif self.ctrl[idx]._type is int:
            self.ctrl[idx].update(value)
        else:
            raise NotImplementedError("{self.ctrl[idx]._type} not supported")
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

    def add_image_placeholder(self, row, col):
        ax_placeholder = None
        image_label = QLabel(self)
        text_label = QLabel(text=f"{row} {col}")
        self.image_canvas[row][col] = {
            "image": image_label,
            "title": text_label,
            "ax_placeholder": ax_placeholder,
        }
        self.image_grid_layout.addWidget(text_label, 2 * row, col, alignment=Qt.AlignmentFlag.AlignCenter)
        self.image_grid_layout.addWidget(image_label, 2 * row + 1, col, alignment=Qt.AlignmentFlag.AlignCenter)

    def delete_image_placeholder(self, img_widget_dict):
        for obj_key, img_widget in img_widget_dict.items():
            if obj_key == "plot_object":
                img_widget = None
            elif obj_key == "ax_placeholder" and img_widget is not None:
                img_widget.remove()
            elif img_widget is not None:
                img_widget.setParent(None)

    def update_image(self, image_array_original, row, col):
        cell = self.image_canvas[row][col]
        if isinstance(image_array_original, np.ndarray) and len(image_array_original.shape) == 1:
            image_array_original = signal_to_curve(image_array_original)
        if isinstance(image_array_original, np.ndarray):
            cell["image"].setPixmap(numpy_to_pixmap(image_array_original))
        elif MPL_SUPPORT and FigureCanvas is not None and isinstance(image_array_original, Curve):
            update_curve_cell(cell, self.image_grid_layout, row, col, image_array_original)
        elif MPL_SUPPORT and FigureCanvas is not None and isinstance(image_array_original, Table):
            update_table_cell(cell, self.image_grid_layout, row, col, image_array_original)
        elif isinstance(image_array_original, str):
            cell["image"].setText(image_array_original)
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
