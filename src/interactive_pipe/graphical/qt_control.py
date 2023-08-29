
from functools import partial
from interactive_pipe.core.control import Control
import logging

PYQTVERSION = None

try:
    from PySide6.QtWidgets import QWidget, QSlider, QHBoxLayout, QLineEdit, QComboBox, QCheckBox, QPushButton, QHBoxLayout
    from PySide6.QtCore import Qt, QSize
    from PySide6.QtGui import QIcon
    PYQTVERSION = 6
except:
    logging.warning("Cannot import PySide")
    
if not PYQTVERSION:
    try:
            from PyQt6.QtWidgets import QWidget, QSlider, QHBoxLayout, QLineEdit, QComboBox, QCheckBox, QPushButton, QHBoxLayout
            from PyQt6.QtCore import Qt, QSize
            from PyQt6.QtGui import QIcon
            PYQTVERSION = 6
    except:
        logging.warning("Cannot import PyQt")
        try:
            from PyQt5.QtWidgets import QWidget, QSlider, QHBoxLayout, QLineEdit, QComboBox, QCheckBox, QPushButton, QHBoxLayout
            from PyQt5.QtCore import Qt, QSize
            from PyQt5.QtGui import QIcon
            PYQTVERSION = 5
        except:
            raise ModuleNotFoundError("No PyQt")


class BaseControl(QWidget):
    def __init__(self, name, ctrl: Control, update_func):
        super().__init__()
        self.name = name
        self.ctrl = ctrl
        self.update_func = update_func
        self.control_widget = None
        self.check_control_type()

    def create(self):
        raise NotImplementedError("This method should be overridden by subclass")

    def check_control_type(self):
        raise NotImplementedError("This method should be overridden by subclass to check the right slider control type")



class IntSliderControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == int

    def create(self):
        slider = QSlider(Qt.Orientation.Horizontal, self)
        slider.setRange(self.ctrl.value_range[0],  self.ctrl.value_range[1])
        slider.setValue(self.ctrl.value_default)
        slider.setSingleStep(5)
        slider.setPageStep(10)
        slider.setTickPosition(QSlider.TickPosition.TicksAbove)
        slider.valueChanged.connect(partial(self.update_func, self.name))
        self.control_widget = slider
        return self.control_widget

class FloatSliderControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == float

    def create(self):
        # Create a horizontal layout to hold the slider and line edit
        hbox = QHBoxLayout()

        # Create the slider with integer range and step size
        slider = QSlider(Qt.Orientation.Horizontal, self)
        slider.setRange(int(self.ctrl.value_range[0] * 100), int(self.ctrl.value_range[1] * 100))
        slider.setValue(int(self.ctrl.value_default * 100))
        slider.setSingleStep(5)
        slider.setPageStep(10)
        slider.setTickPosition(QSlider.TickPosition.TicksAbove)

        # Create a line edit to display the float value
        self.display_widget = QLineEdit()
        self.display_widget.setReadOnly(True)
        self.display_widget.setText(str(self.ctrl.value_default))

        # Connect the slider's value changed signal to update the line edit
        slider.valueChanged.connect(partial(self.update_func, self.name, self.display_widget))

        # Add the slider and line edit to the horizontal layout
        hbox.addWidget(slider)
        hbox.addWidget(self.display_widget)

        self.control_widget = slider

        return hbox


class IconButtonsControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == str
        if not hasattr(self.ctrl, 'value_range') or not hasattr(self.ctrl, 'icons'):
            raise ValueError("Invalid control type or missing value range for icons bar creation.")
        
    def create(self):
        # Check if ctrl has the right type
        
        
        # Create a horizontal layout to hold the icon buttons
        hbox = QHBoxLayout()

        # Iterate over the ctrl's value range to create buttons with icons
        for idx, icon_name in enumerate(self.ctrl.value_range):
            btn = QPushButton(self)
            icon_path = str(self.ctrl.icons[idx])  # Assuming you have a folder named 'icons' with images named after the ctrl's value range
            btn.setIcon(QIcon(icon_path))
            btn.setIconSize(QSize(64, 64))  # Example size, adjust as needed
            # btn.setCheckable(True)  # Making the button checkable if you want to show which one is currently selected

            # Connect the button's clicked signal to some update function
            btn.clicked.connect(partial(self.update_func, self.name, idx))
            
            hbox.addWidget(btn)

        return hbox

class DropdownMenuControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == str
        if not hasattr(self.ctrl, 'value_range'):
            raise ValueError("Invalid control type")

    def create(self):
        # Create a horizontal layout to hold the dropdown menu
        hbox = QHBoxLayout()

        # Create the combo box
        combo_box = QComboBox(self)
        
        # Add items from the ctrl's value range to the combo box
        for item in self.ctrl.value_range:
            combo_box.addItem(item)
        
        # Set the default value for the combo box
        index = combo_box.findText(self.ctrl.value_default)
        if index >= 0:
            combo_box.setCurrentIndex(index)
        
        # Connect the combo box's value changed signal to some update function if needed
        combo_box.currentIndexChanged.connect(partial(self.update_func, self.name))
        # Add the combo box to the horizontal layout
        hbox.addWidget(combo_box)
        return hbox


class TickBoxControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == bool
    def create(self):
        hbox = QHBoxLayout()

        # Create the checkbox
        checkbox = QCheckBox(self.name, self)
        
        # Set the default state for the checkbox based on ctrl's default value
        checkbox.setChecked(self.ctrl.value_default)
        checkbox.stateChanged.connect(partial(self.update_func, self.ctrl.name))

        # Add the checkbox to the horizontal layout
        hbox.addWidget(checkbox)
        return hbox



