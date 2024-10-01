
from functools import partial
from interactive_pipe.headless.control import Control
import logging

PYQTVERSION = None


if not PYQTVERSION:
    try:
        from PyQt6.QtWidgets import QWidget, QLabel, QSlider, QHBoxLayout, QLineEdit, QComboBox, QCheckBox, QPushButton, QHBoxLayout, QDial
        from PyQt6.QtCore import Qt, QSize
        from PyQt6.QtGui import QIcon
        PYQTVERSION = 6
    except ImportError:
        logging.warning("Cannot import PyQt")
        try:
            from PyQt5.QtWidgets import QWidget, QLabel, QSlider, QHBoxLayout, QLineEdit, QComboBox, QCheckBox, QPushButton, QHBoxLayout, QDial
            from PyQt5.QtCore import Qt, QSize
            from PyQt5.QtGui import QIcon
            PYQTVERSION = 5
        except ImportError:
            raise ModuleNotFoundError("No PyQt")
if not PYQTVERSION:
    try:
        from PySide6.QtWidgets import QWidget, QLabel, QSlider, QHBoxLayout, QLineEdit, QComboBox, QCheckBox, QPushButton, QHBoxLayout, QDial
        from PySide6.QtCore import Qt, QSize
        from PySide6.QtGui import QIcon
        PYQTVERSION = 6
    except ImportError:
        logging.warning("Cannot import PySide")

class BaseControl(QWidget):
    def __init__(self, name, ctrl: Control, update_func, silent=False):
        super().__init__()
        self.name = name
        self.ctrl = ctrl
        self.update_func = update_func
        self.control_widget = None
        self.silent = silent
        self.check_control_type()

    def create(self):
        raise NotImplementedError(
            "This method should be overridden by subclass")

    def check_control_type(self):
        raise NotImplementedError(
            "This method should be overridden by subclass to check the right slider control type")


class ControlFactory:
    @staticmethod
    def create_control(control: Control, update_func):
        control_type = control._type
        name = control.name
        control_class_map = {
            bool: TickBoxControl,
            int: IntSliderControl,
            float: FloatSliderControl,
            str: DropdownMenuControl if control.icons is None else IconButtonsControl
        }

        if control_type not in control_class_map:
            logging.warning(
                f"Unsupported control type: {control_type} for control named {name}")
            return None

        control_class = control_class_map[control_type]
        return control_class(name, control, update_func)


class SilentSlider(QSlider):
    def __init__(self, *args, silent_keys=(Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up,  Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown), **kwargs):
        super().__init__(*args, **kwargs)
        self.silent_keys = silent_keys

    def keyPressEvent(self, event):
        if event.key() in self.silent_keys:
            return
        super(SilentSlider, self).keyPressEvent(event)


class IntSliderControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == int

    def create(self):
        if self.silent:
            slider_class = SilentSlider
            slider = slider_class(Qt.Orientation.Horizontal, self)
        else:
            if hasattr(self.ctrl, 'modulo') and self.ctrl.modulo:
                slider_class = QDial
                slider = slider_class(self)
            else:
                slider_class = QSlider
                slider = slider_class(Qt.Orientation.Horizontal, self)
                
        slider.setRange(self.ctrl.value_range[0],  self.ctrl.value_range[1])
        slider.setValue(self.ctrl.value_default)
        slider.setSingleStep(1)
        slider.setPageStep(10)
        # slider.setTickPosition(QSlider.TickPosition.TicksAbove)
        slider.valueChanged.connect(partial(self.update_func, self.name))
        self.control_widget = slider
        return self.control_widget

    def reset(self):
        self.control_widget.setValue(self.ctrl.value)


class FloatSliderControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == float

    def convert_value_to_int(self, val):
        return int((val-self.ctrl.value_range[0])*1000/(self.ctrl.value_range[1]-self.ctrl.value_range[0]))

    def convert_int_to_value(self, val):
        return self.ctrl.value_range[0] + (self.ctrl.value_range[1]-self.ctrl.value_range[0])*val/1000

    def create(self):
        if self.silent:
            slider_class = SilentSlider
            slider = slider_class(Qt.Orientation.Horizontal, self)
        else:
            if hasattr(self.ctrl, 'modulo') and self.ctrl.modulo:
                slider_class = QDial
                slider = slider_class(self)
            else:
                slider_class = QSlider
                slider = slider_class(Qt.Orientation.Horizontal, self)
        self.ctrl.convert_int_to_value = self.convert_int_to_value
        slider.setRange(self.convert_value_to_int(
            self.ctrl.value_range[0]), self.convert_value_to_int(self.ctrl.value_range[1]))
        slider.setValue(self.convert_value_to_int(self.ctrl.value_default))
        slider.setSingleStep(1)
        slider.setPageStep(10)
        # slider.setTickPosition(QSlider.TickPosition.TicksAbove)

        # Connect the slider's value changed signal to update the line edit
        slider.valueChanged.connect(partial(self.update_func, self.name))

        # Add the slider and line edit to the horizontal layout
        # hbox.addWidget(slider)

        self.control_widget = slider
        # return hbox
        return slider

    def reset(self):
        self.control_widget.setValue(
            self.convert_value_to_int(self.ctrl.value))


class IconButtonsControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == str
        if not hasattr(self.ctrl, 'value_range') or not hasattr(self.ctrl, 'icons'):
            raise ValueError(
                "Invalid control type or missing value range for icons bar creation.")

    def create(self):
        # Check if ctrl has the right type

        # Create a horizontal layout to hold the icon buttons
        hbox = QHBoxLayout()
        self.control_widgets = []
        # Iterate over the ctrl's value range to create buttons with icons
        for idx, icon_name in enumerate(self.ctrl.value_range):
            btn = QPushButton(self)
            # Assuming you have a folder named 'icons' with images named after the ctrl's value range
            icon_path = str(self.ctrl.icons[idx])
            btn.setIcon(QIcon(icon_path))
            btn.setIconSize(QSize(64, 64))  # Example size, adjust as needed
            # btn.setCheckable(True)  # Making the button checkable if you want to show which one is currently selected

            # Connect the button's clicked signal to some update function
            btn.clicked.connect(partial(self.update_func, self.name, idx))
            self.control_widgets.append(btn)
            hbox.addWidget(btn)

        return hbox

    def reset(self):
        for _widget in self.control_widgets:
            pass


class DropdownMenuControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == str
        if not hasattr(self.ctrl, 'value_range'):
            raise ValueError("Invalid control type")

    def create(self):
        # Create a horizontal layout to hold the dropdown menu
        hbox = QHBoxLayout()

        # Create the combo box
        self.control_widget = QComboBox(self)
        # Add items from the ctrl's value range to the combo box
        for item in self.ctrl.value_range:
            self.control_widget.addItem(item)
        self.reset()

        # Connect the combo box's value changed signal to some update function if needed
        self.control_widget.currentIndexChanged.connect(
            partial(self.update_func, self.name))
        # Add the combo box to the horizontal layout
        hbox.addWidget(self.control_widget)
        label = QLabel(self.name, self)
        hbox.addWidget(label)
        return hbox
        # return self.control_widget

    def reset(self):
        index = self.control_widget.findText(self.ctrl.value)
        if index >= 0:
            self.control_widget.setCurrentIndex(index)
        self.control_widget.setCurrentIndex(index)


class TickBoxControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == bool

    def create(self):
        hbox = QHBoxLayout()

        # Create the checkbox
        self.control_widget = QCheckBox(self.name, self)

        # Set the default state for the checkbox based on ctrl's default value
        self.reset()
        self.control_widget.stateChanged.connect(
            partial(self.update_func, self.ctrl.name))

        # Add the checkbox to the horizontal layout
        hbox.addWidget(self.control_widget)
        return hbox

    def reset(self):
        self.control_widget.setChecked(self.ctrl.value)
