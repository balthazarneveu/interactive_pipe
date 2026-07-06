"""Recursive panel/control widget building for the Qt GUI backend.

Extracted from MainWindow (tech-debt item 1). QtPanelBuilder is stateless:
every registry it touches (widget_list, name_label, result_label, timer)
lives on the window, exactly as when this code was inline in qt_gui.py.
MainWindow keeps thin `_build_panel_widget`/`_create_control_widget`
delegates with unchanged signatures (DetachedPanelWindow calls them).
"""

import logging
from typing import TYPE_CHECKING, Optional

from interactive_pipe.graphical.qt_backend import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QTimer,
    QVBoxLayout,
    QWidget,
)
from interactive_pipe.graphical.qt_control import ControlFactory
from interactive_pipe.graphical.qt_widgets import CollapsibleBox
from interactive_pipe.headless.control import Control, TimeControl
from interactive_pipe.headless.keyboard import KeyboardControl
from interactive_pipe.headless.panel import Panel

if TYPE_CHECKING:
    from interactive_pipe.graphical.qt_gui import MainWindow


class QtPanelBuilder:
    def __init__(self, window: "MainWindow", control_factory: ControlFactory):
        self.window = window
        self.control_factory = control_factory

    def build_element_widget(self, element) -> Optional[QWidget]:
        """Build widget for an element (Panel or Control).

        Returns:
            QWidget or None if element should be skipped
        """
        if isinstance(element, Panel):
            return self.build_panel_widget(element)
        elif isinstance(element, Control):
            return self.create_control_widget(element)
        return None

    def build_panel_widget(self, panel: Panel) -> QWidget:
        """Recursively build Qt widget for a Panel.

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
                        widget = self.build_element_widget(element)
                        if widget is not None:
                            layout.addWidget(widget, row_idx, col_idx)
        elif panel.elements:
            # Vertical layout: flat list
            layout = QVBoxLayout()
            layout.setSpacing(8)  # Nice spacing between controls
            for element in panel.elements:
                widget = self.build_element_widget(element)
                if widget is not None:
                    layout.addWidget(widget)
        else:
            # No child elements, just a simple vertical layout for controls
            layout = QVBoxLayout()
            layout.setSpacing(8)  # Nice spacing between controls

        # Add controls assigned directly to this panel
        for ctrl in panel._controls:
            widget = self.create_control_widget(ctrl)
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

    def create_control_widget(self, ctrl: Control) -> Optional[QWidget]:
        """Create a single control widget row with labels.
        Returns the row container widget or None if control should be skipped."""
        window = self.window
        slider_name = ctrl.name

        if isinstance(ctrl, KeyboardControl):
            if window.main_gui is not None:
                window.main_gui.bind_keyboard_slider(ctrl, window.key_update_parameter)  # type: ignore[reportOptionalMemberAccess]
            return None
        elif isinstance(ctrl, TimeControl):
            window.timer = QTimer(window)

            def suspend_resume_timer(suspend: bool):
                if suspend:
                    logging.debug("Suspend")
                    window.timer.stop()
                else:
                    logging.debug("Resume")
                    window.timer.start()

            if window.main_gui is not None:
                window.main_gui.suspend_resume_timer = suspend_resume_timer  # type: ignore[reportOptionalMemberAccess]
                plugged_func = window.main_gui.plug_timer_control(ctrl, window.update_parameter, suspend_resume_timer)  # type: ignore[reportOptionalMemberAccess]
            else:

                def plugged_func():
                    pass

            window.timer.timeout.connect(plugged_func)
            window.timer.start(ctrl.update_interval_ms)
            return None
        elif isinstance(ctrl, Control):
            slider_instance = self.control_factory.create_control(ctrl, window.update_parameter)
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
            window.widget_list[slider_name] = slider_instance

            slider_layout = QHBoxLayout()
            slider_layout.setSpacing(8)  # Nice spacing between label, slider, and value

            if isinstance(slider_or_layout, QWidget):
                # Balanced label width that works well in both panels and bottom area
                label_fixed_width = 150
                label = QLabel("", window)
                label.setMinimumWidth(label_fixed_width)
                window.name_label[slider_name] = label
                slider_layout.addWidget(window.name_label[slider_name])
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
                label = QLabel("", window)
                label.setMinimumWidth(result_fixed_width)
                window.result_label[slider_name] = label
                slider_layout.addWidget(window.result_label[slider_name])

            # Create a container widget for the entire row
            row_container_widget = QWidget()
            row_container_widget.setLayout(slider_layout)
            row_container_widget.setContentsMargins(0, 0, 0, 0)

            window.update_label(slider_name)
            return row_container_widget
        return None
