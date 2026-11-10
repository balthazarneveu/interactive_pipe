import logging
from functools import partial
from typing import Optional

from interactive_pipe.headless.control import Control, RangeControl, range_pair

# Qt symbols come from the shared binding cascade in qt_backend; unlike the GUI
# modules this one stays importable without any Qt binding (the factory then
# raises ModuleNotFoundError when a widget is requested).
try:
    from interactive_pipe.graphical.qt_backend import (
        PYQTVERSION,
        QCheckBox,
        QComboBox,
        QDial,
        QDoubleSpinBox,
        QHBoxLayout,
        QIcon,
        QLabel,
        QLineEdit,
        QPainter,
        QPen,
        QPushButton,
        QRectF,
        QSize,
        QSlider,
        QSpinBox,
        Qt,
        QVBoxLayout,
        QWidget,
    )

    PYQT_AVAILABLE = True
except ModuleNotFoundError:
    PYQTVERSION = None
    PYQT_AVAILABLE = False
    QWidget = None
    QLabel = None
    QSlider = None
    QHBoxLayout = None
    QVBoxLayout = None
    QLineEdit = None
    QComboBox = None
    QCheckBox = None
    QPushButton = None
    QDial = None
    QSpinBox = None
    QDoubleSpinBox = None
    Qt = None
    QSize = None
    QIcon = None
    logging.warning("PyQt not available. Qt controls will not work.")


class BaseControl(QWidget if PYQT_AVAILABLE else object):  # type: ignore[reportGeneralTypeIssues]
    """Qt widget wrapper for one Control.

    Widgets always hand ``update_func(name, value)`` a value expressed in the
    control's own domain (float for a float slider, the chosen string for a
    dropdown, bool for a tick box): the window applies it with ``Control.update``
    without knowing which widget produced it.
    """

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
        if isinstance(control, RangeControl):
            return RangeSliderControl(name, control, update_func)

        control_class_map = {
            bool: TickBoxControl,
            int: IntSliderControl if control.value_range is not None else IntSpinBoxControl,
            float: FloatSliderControl if control.value_range is not None else FloatSpinBoxControl,
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
            super().keyPressEvent(event)

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
        step = self.ctrl.step if self.ctrl.step else 1
        if not isinstance(step, int):
            raise TypeError(f"Expected int for IntSliderControl step, got {type(step)}")
        slider.setSingleStep(step)
        slider.setPageStep(step)
        # slider.setTickPosition(QSlider.TickPosition.TicksAbove)
        slider.valueChanged.connect(partial(self._on_value_changed, valmin, step))
        if self.ctrl.tooltip:
            slider.setToolTip(self.ctrl.tooltip)
        self.control_widget = slider
        return self.control_widget

    def _on_value_changed(self, valmin, step, value):
        snapped = valmin + round((value - valmin) / step) * step
        self.update_func(self.name, snapped)

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
        value_min, value_max = self.ctrl.value_range[0], self.ctrl.value_range[1]  # type: ignore[reportOptionalSubscript]
        if value_max == value_min:
            return 0
        return int(round((val - value_min) * 1000 / (value_max - value_min)))  # type: ignore[reportOperatorIssue]

    def convert_int_to_value(self, val):
        if self.ctrl.value_range is None:
            raise ValueError("value_range must be set for FloatSliderControl")
        value_min = self.ctrl.value_range[0]  # type: ignore[reportOptionalSubscript]
        value_max = self.ctrl.value_range[1]  # type: ignore[reportOptionalSubscript]
        value = value_min + (value_max - value_min) * val / 1000  # type: ignore[reportOperatorIssue]
        step = self.ctrl.step
        if step:
            value = round((value - value_min) / step) * step + value_min
        return value

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
        slider.setRange(
            self.convert_value_to_int(self.ctrl.value_range[0]),  # type: ignore[reportOptionalSubscript]
            self.convert_value_to_int(self.ctrl.value_range[1]),  # type: ignore[reportOptionalSubscript]
        )
        valdefault = self.ctrl.value_default
        if not isinstance(valdefault, (int, float)):
            raise TypeError(f"Expected int or float for FloatSliderControl default, got {type(valdefault)}")
        slider.setValue(self.convert_value_to_int(valdefault))
        value_min = self.ctrl.value_range[0]  # type: ignore[reportOptionalSubscript]
        value_max = self.ctrl.value_range[1]  # type: ignore[reportOptionalSubscript]
        if not isinstance(value_min, (int, float)) or not isinstance(value_max, (int, float)):
            raise TypeError(
                f"Expected int or float for FloatSliderControl range, got {type(value_min)}, {type(value_max)}"
            )
        int_step = max(1, round(self.ctrl.step / (value_max - value_min) * 1000)) if self.ctrl.step else 1
        slider.setSingleStep(int_step)
        slider.setPageStep(int_step)
        # slider.setTickPosition(QSlider.TickPosition.TicksAbove)

        # the slider works on an integer scale: convert back to the float domain
        slider.valueChanged.connect(self._on_value_changed)

        if self.ctrl.tooltip:
            slider.setToolTip(self.ctrl.tooltip)
        self.control_widget = slider
        return slider

    def _on_value_changed(self, slider_position: int):
        self.update_func(self.name, self.convert_int_to_value(slider_position))

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
        # one checkable button per choice; the checked one shows the current value
        self.control_widgets = []
        for idx, choice in enumerate(self.ctrl.value_range):  # type: ignore[reportArgumentType]
            btn = QPushButton(self)
            btn.setIcon(QIcon(str(self.ctrl.icons[idx])))  # type: ignore[reportOptionalSubscript]
            btn.setIconSize(QSize(64, 64))
            btn.setCheckable(True)
            btn.setToolTip(self.ctrl.tooltip or str(choice))
            btn.clicked.connect(partial(self._on_click, choice))
            self.control_widgets.append(btn)
            hbox.addWidget(btn)
        self.reset()
        return hbox

    def _on_click(self, choice):
        self._check_only(choice)
        self.update_func(self.name, choice)

    def _check_only(self, choice):
        for btn, btn_choice in zip(self.control_widgets, self.ctrl.value_range):  # type: ignore[reportArgumentType]
            btn.setChecked(btn_choice == choice)

    def reset(self):
        self._check_only(self.ctrl.value)


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

        self.control_widget.currentIndexChanged.connect(self._on_index_changed)
        if self.ctrl.tooltip:
            self.control_widget.setToolTip(self.ctrl.tooltip)
        # Add the combo box to the horizontal layout
        hbox.addWidget(self.control_widget)
        label = QLabel(self.name, self)
        hbox.addWidget(label)
        return hbox
        # return self.control_widget

    def _on_index_changed(self, index: int):
        self.update_func(self.name, self.ctrl.value_range[index])  # type: ignore[reportOptionalSubscript]

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
        self.control_widget.stateChanged.connect(lambda state: self.update_func(self.name, bool(state)))

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


class _SpinBoxControl(BaseControl):
    """Numeric entry for a control declared without value_range (free parameter)."""

    _widget_class = None  # set by subclasses (QSpinBox / QDoubleSpinBox)
    _bounds = (-(2**31), 2**31 - 1)

    def check_control_type(self):
        if self.ctrl.value_range is not None:
            raise ValueError(f"{type(self).__name__} is meant for controls without value_range")

    def create(self):
        widget_class = self._widget_class
        if widget_class is None:
            raise ModuleNotFoundError("PyQt is required for Qt controls")
        spin_box = widget_class(self)
        spin_box.setRange(*self._bounds)
        self._configure(spin_box)
        spin_box.setValue(self.ctrl.value)
        spin_box.valueChanged.connect(partial(self.update_func, self.name))
        if self.ctrl.tooltip:
            spin_box.setToolTip(self.ctrl.tooltip)
        self.control_widget = spin_box
        return spin_box

    def _configure(self, spin_box):
        if self.ctrl.step:
            spin_box.setSingleStep(self.ctrl.step)

    def reset(self):
        self.control_widget.setValue(self.ctrl.value)


class IntSpinBoxControl(_SpinBoxControl):
    _widget_class = QSpinBox

    def check_control_type(self):
        if self.ctrl._type is not int:
            raise TypeError(f"Expected int control type, got {self.ctrl._type}")
        super().check_control_type()


class FloatSpinBoxControl(_SpinBoxControl):
    _widget_class = QDoubleSpinBox
    _bounds = (-1e12, 1e12)

    def check_control_type(self):
        if self.ctrl._type is not float:
            raise TypeError(f"Expected float control type, got {self.ctrl._type}")
        super().check_control_type()

    def _configure(self, spin_box):
        spin_box.setDecimals(4)
        spin_box.setSingleStep(self.ctrl.step if self.ctrl.step else 0.1)


class TwoHandleSlider(QWidget if PYQT_AVAILABLE else object):  # type: ignore[reportGeneralTypeIssues]
    """One track with two draggable handles (integer positions ``0..ticks``).

    The handle being dragged pushes the other one along, so ``low <= high``
    always holds. ``on_change(low, high)`` fires on every user move.
    Arrow keys / Home / End move the last used handle.
    """

    HANDLE_RADIUS = 8
    GROOVE_HEIGHT = 4

    def __init__(self, ticks: int, low: int = 0, high: Optional[int] = None, on_change=None, parent=None):
        super().__init__(parent)  # type: ignore[call-arg]
        self._ticks = max(1, int(ticks))
        self._low = 0
        self._high = self._ticks
        self._active = "high"
        self.on_change = on_change
        self.setMinimumHeight(2 * self.HANDLE_RADIUS + 6)
        self.setMinimumWidth(6 * self.HANDLE_RADIUS)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # type: ignore[union-attr]
        self.set_values(low, self._ticks if high is None else high)

    # -- values -------------------------------------------------------------
    def low(self) -> int:
        return self._low

    def high(self) -> int:
        return self._high

    def maximum(self) -> int:
        return self._ticks

    def set_values(self, low: int, high: int) -> None:
        """Set both handles without notifying ``on_change``."""
        low, high = sorted((max(0, min(self._ticks, int(low))), max(0, min(self._ticks, int(high)))))
        self._low, self._high = low, high
        self.update()

    def _move(self, which: str, position: int) -> None:
        position = max(0, min(self._ticks, position))
        low, high = self._low, self._high
        if which == "low":
            low, high = position, max(high, position)
        else:
            low, high = min(low, position), position
        self._active = which
        if (low, high) != (self._low, self._high):
            self._low, self._high = low, high
            self.update()
            if self.on_change is not None:
                self.on_change(low, high)

    # -- geometry -----------------------------------------------------------
    def _x_of(self, position: int) -> float:
        margin = self.HANDLE_RADIUS + 1
        return margin + (self.width() - 2 * margin) * position / self._ticks

    def _position_at(self, x: float) -> int:
        margin = self.HANDLE_RADIUS + 1
        usable = max(1, self.width() - 2 * margin)
        return int(round(self._ticks * (x - margin) / usable))

    def sizeHint(self):
        return QSize(160, 2 * self.HANDLE_RADIUS + 8)  # type: ignore[misc]

    # -- events -------------------------------------------------------------
    def _x_of_event(self, event) -> float:
        return event.position().x() if hasattr(event, "position") else float(event.x())

    def mousePressEvent(self, event):  # noqa: N802
        x = self._x_of_event(event)
        d_low, d_high = abs(x - self._x_of(self._low)), abs(x - self._x_of(self._high))
        if d_low == d_high:  # stacked handles: pick the one that can move toward the click
            which = "low" if x < self._x_of(self._low) else "high"
        else:
            which = "low" if d_low < d_high else "high"
        self._drag = which
        self.setFocus()
        self._move(which, self._position_at(x))

    def mouseMoveEvent(self, event):  # noqa: N802
        which = getattr(self, "_drag", None)
        if which is not None:
            self._move(which, self._position_at(self._x_of_event(event)))

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._drag = None

    def keyPressEvent(self, event):  # noqa: N802
        key = event.key()
        current = self._low if self._active == "low" else self._high
        K = Qt.Key  # type: ignore[union-attr]
        if key in (K.Key_Left, K.Key_Down):
            self._move(self._active, current - 1)
        elif key in (K.Key_Right, K.Key_Up):
            self._move(self._active, current + 1)
        elif key == K.Key_Home:
            self._move(self._active, 0)
        elif key == K.Key_End:
            self._move(self._active, self._ticks)
        else:
            super().keyPressEvent(event)  # type: ignore[misc]

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)  # type: ignore[misc]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)  # type: ignore[union-attr]
        palette = self.palette()
        highlight = palette.highlight().color()
        base = palette.base().color()
        groove_color = palette.mid().color()
        cy = self.height() / 2
        x_low, x_high = self._x_of(self._low), self._x_of(self._high)
        half = self.GROOVE_HEIGHT / 2
        painter.setPen(Qt.PenStyle.NoPen)  # type: ignore[union-attr]
        painter.setBrush(groove_color)
        painter.drawRoundedRect(
            QRectF(self._x_of(0), cy - half, self._x_of(self._ticks) - self._x_of(0), self.GROOVE_HEIGHT),  # type: ignore[misc]
            half,
            half,
        )
        painter.setBrush(highlight)
        painter.drawRect(QRectF(x_low, cy - half, max(0.0, x_high - x_low), self.GROOVE_HEIGHT))  # type: ignore[misc]
        for which, x in (("low", x_low), ("high", x_high)):
            focused = self.hasFocus() and which == self._active
            pen = QPen(highlight.lighter(130) if focused else highlight, 2)  # type: ignore[misc]
            painter.setPen(pen)
            painter.setBrush(base)
            r = self.HANDLE_RADIUS - 1
            painter.drawEllipse(QRectF(x - r, cy - r, 2 * r, 2 * r))  # type: ignore[misc]
        painter.end()


class RangeSliderControl(BaseControl):
    """Single-track two-handle slider (``TwoHandleSlider``) for a RangeControl.

    Positions live on an integer grid (one tick per ``step``). Dragging one
    handle past the other pushes it along, so ``lo <= hi`` always holds;
    ``update_func`` receives the ``(lo, hi)`` tuple.
    """

    def check_control_type(self):
        if not isinstance(self.ctrl, RangeControl):
            raise TypeError(f"Expected a RangeControl, got {type(self.ctrl)}")

    def _ticks(self) -> int:
        value_min, value_max = self.ctrl.value_range  # type: ignore[misc]
        return max(1, int(round((value_max - value_min) / self.ctrl.step)))  # type: ignore[operator]

    def to_position(self, value) -> int:
        value_min = self.ctrl.value_range[0]  # type: ignore[index]
        return max(0, min(self._ticks(), int(round((value - value_min) / self.ctrl.step))))  # type: ignore[operator]

    def to_value(self, position: int):
        value_min, value_max = self.ctrl.value_range  # type: ignore[misc]
        value = min(value_min + position * self.ctrl.step, value_max)  # type: ignore[operator]
        return int(value) if self.ctrl._type is int else round(float(value), 12)

    def create(self):
        if QWidget is None:
            raise ModuleNotFoundError("PyQt is required for Qt controls")
        self.range_slider = TwoHandleSlider(self._ticks(), on_change=self._on_changed, parent=self)
        if self.ctrl.tooltip:
            self.range_slider.setToolTip(self.ctrl.tooltip)
        self.control_widget = self.range_slider
        self.reset()
        return self.range_slider

    def _on_changed(self, low: int, high: int):
        self.update_func(self.name, (self.to_value(low), self.to_value(high)))

    def reset(self):
        lo, hi = range_pair(self.ctrl)
        self.range_slider.set_values(self.to_position(lo), self.to_position(hi))
