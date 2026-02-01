import logging
from functools import partial

from interactive_pipe.headless.control import Control

PYQTVERSION = None
PYQT_AVAILABLE = False

if not PYQTVERSION:
    try:
        from PyQt6.QtCore import QSize, Qt  # noqa: F811
        from PyQt6.QtGui import QIcon  # noqa: F811
        from PyQt6.QtWidgets import (  # noqa: F811
            QCheckBox,
            QComboBox,
            QDial,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            QSlider,
            QWidget,
        )

        PYQTVERSION = 6
        PYQT_AVAILABLE = True
    except ImportError:
        logging.warning("Cannot import PyQt6")
        try:
            from PyQt5.QtCore import QSize, Qt
            from PyQt5.QtGui import QIcon
            from PyQt5.QtWidgets import (  # noqa: F811
                QCheckBox,
                QComboBox,
                QDial,
                QHBoxLayout,
                QLabel,
                QLineEdit,
                QPushButton,
                QSlider,
                QWidget,
            )

            PYQTVERSION = 5
            PYQT_AVAILABLE = True
        except ImportError:
            logging.warning("Cannot import PyQt5")
if not PYQTVERSION:
    try:
        from PySide6.QtCore import QSize, Qt  # noqa: F811
        from PySide6.QtGui import QIcon  # noqa: F811
        from PySide6.QtWidgets import (  # noqa: F811
            QCheckBox,
            QComboBox,
            QDial,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            QSlider,
            QWidget,
        )

        PYQTVERSION = 6
        PYQT_AVAILABLE = True
    except ImportError:
        logging.warning("Cannot import PySide6")

if not PYQT_AVAILABLE:
    # Create dummy classes to allow import even when PyQt is not available
    QWidget = None  # noqa: F811
    QLabel = None  # noqa: F811
    QSlider = None  # noqa: F811
    QHBoxLayout = None  # noqa: F811
    QLineEdit = None  # noqa: F811
    QComboBox = None  # noqa: F811
    QCheckBox = None  # noqa: F811
    QPushButton = None  # noqa: F811
    QDial = None  # noqa: F811
    Qt = None  # noqa: F811
    QSize = None  # noqa: F811
    QIcon = None  # noqa: F811
    logging.warning("PyQt not available. Qt controls will not work.")


class BaseControl(QWidget if PYQT_AVAILABLE else object):  # type: ignore[reportGeneralTypeIssues]
    def __init__(self, name, ctrl: Control, update_func, silent=False):
        if not PYQT_AVAILABLE:
            raise ModuleNotFoundError(
                "PyQt is required for Qt controls. "
                "Install it with: pip install interactive-pipe[qt6] or interactive-pipe[qt5]"
            )
        if PYQT_AVAILABLE and QWidget is not None:
            super().__init__()
        else:
            object.__init__(self)
        self.name = name
        self.ctrl = ctrl
        self.update_func = update_func
        self.control_widget = None
        self.silent = silent
        self.check_control_type()

    def create(self):
        raise NotImplementedError("This method should be overridden by subclass")

    def check_control_type(self):
        raise NotImplementedError("This method should be overridden by subclass to check the right slider control type")


class ControlFactory:
    @staticmethod
    def create_control(control: Control, update_func):
        control_type = control._type
        name = control.name
        # Return None for single-value controls (don't show anything)
        if control_type is str and control.value_range is not None and len(control.value_range) == 1:
            return None

        control_class_map = {
            bool: TickBoxControl,
            int: IntSliderControl,
            float: FloatSliderControl,
            str: (
                PromptControl
                if control.value_range is None
                else (DropdownMenuControl if control.icons is None else IconButtonsControl)
            ),
        }

        if control_type not in control_class_map:
            logging.warning(f"Unsupported control type: {control_type} for control named {name}")
            return None

        control_class = control_class_map[control_type]
        return control_class(name, control, update_func)


if PYQT_AVAILABLE:

    class SilentSlider(QSlider):  # type: ignore[reportGeneralTypeIssues]
        def __init__(
            self,
            *args,
            silent_keys=(
                Qt.Key.Key_Left,  # type: ignore[reportOptionalMemberAccess]
                Qt.Key.Key_Right,  # type: ignore[reportOptionalMemberAccess]
                Qt.Key.Key_Up,  # type: ignore[reportOptionalMemberAccess]
                Qt.Key.Key_Down,  # type: ignore[reportOptionalMemberAccess]
                Qt.Key.Key_PageUp,  # type: ignore[reportOptionalMemberAccess]
                Qt.Key.Key_PageDown,  # type: ignore[reportOptionalMemberAccess]
            ),
            **kwargs,
        ):
            super().__init__(*args, **kwargs)
            self.silent_keys = silent_keys

        def keyPressEvent(self, event):
            if event.key() in self.silent_keys:
                return
            super(SilentSlider, self).keyPressEvent(event)

else:
    SilentSlider = None  # type: ignore[reportAssignmentType]


class IntSliderControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type is not int:
            raise TypeError(f"Expected int control type, got {self.ctrl._type}")

    def create(self):
        if self.ctrl.value_range is None:
            raise ValueError("value_range must be set for IntSliderControl")
        if self.silent:
            slider_class = SilentSlider
            if slider_class is None or Qt is None:
                raise ModuleNotFoundError("PyQt is required for Qt controls")
            slider = slider_class(Qt.Orientation.Horizontal, self)  # type: ignore[reportOptionalCall,reportOptionalMemberAccess]
        else:
            if hasattr(self.ctrl, "modulo") and self.ctrl.modulo:  # type: ignore[reportAttributeAccessIssue]
                if QDial is None:
                    raise ModuleNotFoundError("PyQt is required for Qt controls")
                slider_class = QDial
                slider = slider_class(self)
            else:
                if QSlider is None or Qt is None:
                    raise ModuleNotFoundError("PyQt is required for Qt controls")
                slider_class = QSlider
                slider = slider_class(Qt.Orientation.Horizontal, self)  # type: ignore[reportOptionalMemberAccess]

        valmin = self.ctrl.value_range[0]  # type: ignore[reportOptionalSubscript]
        valmax = self.ctrl.value_range[1]  # type: ignore[reportOptionalSubscript]
        valdefault = self.ctrl.value_default
        if not isinstance(valmin, int) or not isinstance(valmax, int):
            raise TypeError(f"Expected int for IntSliderControl range, got {type(valmin)}, {type(valmax)}")
        if not isinstance(valdefault, int):
            raise TypeError(f"Expected int for IntSliderControl default, got {type(valdefault)}")
        slider.setRange(valmin, valmax)
        slider.setValue(valdefault)
        slider.setSingleStep(1)
        slider.setPageStep(10)
        # slider.setTickPosition(QSlider.TickPosition.TicksAbove)
        slider.valueChanged.connect(partial(self.update_func, self.name))
        if self.ctrl.tooltip:
            slider.setToolTip(self.ctrl.tooltip)
        self.control_widget = slider
        return self.control_widget

    def reset(self):
        value = self.ctrl.value
        if not isinstance(value, int):
            raise TypeError(f"Expected int for IntSliderControl value, got {type(value)}")
        self.control_widget.setValue(value)


class FloatSliderControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type is not float:
            raise TypeError(f"Expected float control type, got {self.ctrl._type}")

    def convert_value_to_int(self, val):
        if self.ctrl.value_range is None:
            raise ValueError("value_range must be set for FloatSliderControl")
        return int((val - self.ctrl.value_range[0]) * 1000 / (self.ctrl.value_range[1] - self.ctrl.value_range[0]))  # type: ignore[reportOptionalSubscript,reportOperatorIssue]

    def convert_int_to_value(self, val):
        if self.ctrl.value_range is None:
            raise ValueError("value_range must be set for FloatSliderControl")
        return self.ctrl.value_range[0] + (self.ctrl.value_range[1] - self.ctrl.value_range[0]) * val / 1000  # type: ignore[reportOptionalSubscript,reportOperatorIssue]

    def create(self):
        if self.ctrl.value_range is None:
            raise ValueError("value_range must be set for FloatSliderControl")
        if self.silent:
            slider_class = SilentSlider
            if slider_class is None or Qt is None:
                raise ModuleNotFoundError("PyQt is required for Qt controls")
            slider = slider_class(Qt.Orientation.Horizontal, self)  # type: ignore[reportOptionalCall,reportOptionalMemberAccess]
        else:
            if hasattr(self.ctrl, "modulo") and self.ctrl.modulo:  # type: ignore[reportAttributeAccessIssue]
                if QDial is None:
                    raise ModuleNotFoundError("PyQt is required for Qt controls")
                slider_class = QDial
                slider = slider_class(self)
            else:
                if QSlider is None or Qt is None:
                    raise ModuleNotFoundError("PyQt is required for Qt controls")
                slider_class = QSlider
                slider = slider_class(Qt.Orientation.Horizontal, self)  # type: ignore[reportOptionalMemberAccess]
        self.ctrl.convert_int_to_value = self.convert_int_to_value  # type: ignore[reportAttributeAccessIssue]
        slider.setRange(
            self.convert_value_to_int(self.ctrl.value_range[0]),  # type: ignore[reportOptionalSubscript]
            self.convert_value_to_int(self.ctrl.value_range[1]),  # type: ignore[reportOptionalSubscript]
        )
        valdefault = self.ctrl.value_default
        if not isinstance(valdefault, (int, float)):
            raise TypeError(f"Expected int or float for FloatSliderControl default, got {type(valdefault)}")
        slider.setValue(self.convert_value_to_int(valdefault))
        slider.setSingleStep(1)
        slider.setPageStep(10)
        # slider.setTickPosition(QSlider.TickPosition.TicksAbove)

        # Connect the slider's value changed signal to update the line edit
        slider.valueChanged.connect(partial(self.update_func, self.name))

        if self.ctrl.tooltip:
            slider.setToolTip(self.ctrl.tooltip)

        # Add the slider and line edit to the horizontal layout
        # hbox.addWidget(slider)

        self.control_widget = slider
        # return hbox
        return slider

    def reset(self):
        self.control_widget.setValue(self.convert_value_to_int(self.ctrl.value))


class IconButtonsControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type is not str:
            raise TypeError(f"Expected str control type, got {self.ctrl._type}")
        if not hasattr(self.ctrl, "value_range") or not hasattr(self.ctrl, "icons"):
            raise ValueError("Invalid control type or missing value range for icons bar creation.")

    def create(self):
        # Check if ctrl has the right type
        if self.ctrl.value_range is None:
            raise ValueError("value_range must be set for IconButtonsControl")
        if self.ctrl.icons is None:
            raise ValueError("icons must be set for IconButtonsControl")
        if QHBoxLayout is None or QPushButton is None or QIcon is None or QSize is None:
            raise ModuleNotFoundError("PyQt is required for Qt controls")

        # Create a horizontal layout to hold the icon buttons
        hbox = QHBoxLayout()
        self.control_widgets = []
        # Iterate over the ctrl's value range to create buttons with icons
        for idx, icon_name in enumerate(self.ctrl.value_range):  # type: ignore[reportArgumentType]
            btn = QPushButton(self)
            # Assuming you have a folder named 'icons' with images named after the ctrl's value range
            icon_path = str(self.ctrl.icons[idx])  # type: ignore[reportOptionalSubscript]
            btn.setIcon(QIcon(icon_path))
            btn.setIconSize(QSize(64, 64))  # Example size, adjust as needed
            # btn.setCheckable(True)  # Making the button checkable if you want to show which one is currently selected

            # Connect the button's clicked signal to some update function
            btn.clicked.connect(partial(self.update_func, self.name, idx))
            if self.ctrl.tooltip:
                btn.setToolTip(self.ctrl.tooltip)
            self.control_widgets.append(btn)
            hbox.addWidget(btn)

        return hbox

    def reset(self):
        for _widget in self.control_widgets:
            pass


class DropdownMenuControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type is not str:
            raise TypeError(f"Expected str control type, got {self.ctrl._type}")
        if not hasattr(self.ctrl, "value_range"):
            raise ValueError("Invalid control type")

    def create(self):
        if self.ctrl.value_range is None:
            raise ValueError("value_range must be set for DropdownMenuControl")
        if QHBoxLayout is None or QComboBox is None or QLabel is None:
            raise ModuleNotFoundError("PyQt is required for Qt controls")
        # Create a horizontal layout to hold the dropdown menu
        hbox = QHBoxLayout()

        # Create the combo box
        self.control_widget = QComboBox(self)
        # Add items from the ctrl's value range to the combo box
        for item in self.ctrl.value_range:
            item_str = str(item) if not isinstance(item, str) else item
            self.control_widget.addItem(item_str)
        self.reset()

        # Connect the combo box's value changed signal to some update function if needed
        self.control_widget.currentIndexChanged.connect(partial(self.update_func, self.name))
        if self.ctrl.tooltip:
            self.control_widget.setToolTip(self.ctrl.tooltip)
        # Add the combo box to the horizontal layout
        hbox.addWidget(self.control_widget)
        label = QLabel(self.name, self)
        hbox.addWidget(label)
        return hbox
        # return self.control_widget

    def reset(self):
        if self.control_widget is None:
            return
        value = self.ctrl.value
        value_str = str(value) if not isinstance(value, str) else value
        index = self.control_widget.findText(value_str)
        if index >= 0:
            self.control_widget.setCurrentIndex(index)
        else:
            # If not found, set to first item or 0
            self.control_widget.setCurrentIndex(0)


class PromptControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type is not str:
            raise TypeError(f"Expected str control type, got {self.ctrl._type}")
        if self.ctrl.value_range is not None:
            raise ValueError("value_range must be None for PromptControl")

    def create(self):
        if QHBoxLayout is None or QLineEdit is None or QLabel is None:
            raise ModuleNotFoundError("PyQt is required for Qt controls")
        # Create a horizontal layout to hold the text prompt
        hbox = QHBoxLayout()

        # Create the line edit (text input field)
        self.control_widget = QLineEdit(self)

        # Set the initial value of the text field if it's provided
        value = self.ctrl.value
        if value:
            value_str = str(value) if not isinstance(value, str) else value
            self.control_widget.setText(value_str)

        # Connect the textChanged signal to the update function if needed
        self.control_widget.textChanged.connect(partial(self.update_func, self.name))

        if self.ctrl.tooltip:
            self.control_widget.setToolTip(self.ctrl.tooltip)

        # Add the text input field to the horizontal layout
        hbox.addWidget(self.control_widget)

        # Add a label to the layout
        label = QLabel(self.name, self)
        hbox.addWidget(label)

        return hbox

    def reset(self):
        # Reset the text field to the initial value
        value = self.ctrl.value
        value_str = str(value) if not isinstance(value, str) else value
        self.control_widget.setText(value_str)


class TickBoxControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type is not bool:
            raise TypeError(f"Expected bool control type, got {self.ctrl._type}")

    def create(self):
        if QHBoxLayout is None or QCheckBox is None:
            raise ModuleNotFoundError("PyQt is required for Qt controls")
        hbox = QHBoxLayout()

        # Create the checkbox
        self.control_widget = QCheckBox(self.name, self)

        # Set the default state for the checkbox based on ctrl's default value
        self.reset()
        self.control_widget.stateChanged.connect(partial(self.update_func, self.ctrl.name))

        if self.ctrl.tooltip:
            self.control_widget.setToolTip(self.ctrl.tooltip)

        # Add the checkbox to the horizontal layout
        hbox.addWidget(self.control_widget)
        return hbox

    def reset(self):
        value = self.ctrl.value
        if not isinstance(value, bool):
            raise TypeError(f"Expected bool for TickBoxControl value, got {type(value)}")
        self.control_widget.setChecked(value)
