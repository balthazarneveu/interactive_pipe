from matplotlib.widgets import Slider, CheckButtons, RadioButtons, TextBox
from interactive_pipe.headless.control import Control
import logging


class BaseControl:
    def __init__(self, name, ctrl: Control, update_func, ax_control=None):
        super().__init__()
        self.name = name
        self.ctrl = ctrl
        self.update_func = update_func
        self.control_widget = None
        self.check_control_type()
        self.ax_control = ax_control

    def create(self):
        raise NotImplementedError("This method should be overridden by subclass")

    def check_control_type(self):
        raise NotImplementedError(
            "This method should be overridden by subclass to check the right slider control type"
        )


class SliderMatplotlibControl(BaseControl):
    def create(self):
        slider = Slider(
            self.ax_control,
            self.name,
            self.ctrl.value_range[0],
            self.ctrl.value_range[1],
            valinit=self.ctrl.value,
            valstep=1 if self.ctrl._type == int else None,
        )
        slider.on_changed(lambda val: self.update_func(self.name, val))
        return slider


class IntSliderMatplotlibControl(SliderMatplotlibControl):
    def check_control_type(self):
        if self.ctrl._type != int:
            raise TypeError(f"Expected int control type, got {self.ctrl._type}")


class FloatSliderMatplotlibControl(SliderMatplotlibControl):
    def check_control_type(self):
        if self.ctrl._type != float:
            raise TypeError(f"Expected float control type, got {self.ctrl._type}")


class BoolCheckButtonMatplotlibControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type != bool:
            raise TypeError(f"Expected bool control type, got {self.ctrl._type}")

    def create(self):
        current_state = [self.ctrl.value]

        def on_click(label):
            current_state[0] = not current_state[0]
            self.update_func(self.name, current_state[0])

        checks = CheckButtons(self.ax_control, [self.name], [self.ctrl.value])
        checks.on_clicked(on_click)
        return checks


class StringRadioButtonMatplotlibControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type != str:
            raise TypeError(f"Expected str control type, got {self.ctrl._type}")
        if self.ctrl.value_range is None:
            raise ValueError(
                "value_range must be provided for StringRadioButtonMatplotlibControl"
            )

    def create(self):
        options = self.ctrl.value_range
        radio = RadioButtons(
            self.ax_control,
            options,
            active=(
                options.index(self.ctrl.value) if self.ctrl.value in options else None
            ),
        )
        radio.on_clicked(lambda val: self.update_func(self.name, val))

        return radio


class PromptMatplotlibControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type != str:
            raise TypeError(f"Expected str control type, got {self.ctrl._type}")
        if self.ctrl.value_range is not None:
            raise ValueError("value_range must be None for PromptMatplotlibControl")

    def create(self):
        # Create a prompt for text input
        self.text_box = TextBox(self.ax_control, "Input", initial=self.ctrl.value)

        # Function to handle the update when text is entered
        def submit(text):
            self.update_func(self.name, text)

        # Connect the submission of the text box to the submit function
        self.text_box.on_submit(submit)

        return self.text_box


class ControlFactory:
    @staticmethod
    def create_control(control: Control, update_func, ax_control=None):
        control_type = control._type
        name = control.name
        # Return None for single-value controls (don't show anything)
        if (
            control_type == str
            and control.value_range is not None
            and len(control.value_range) == 1
        ):
            return None

        control_class_map = {
            bool: BoolCheckButtonMatplotlibControl,
            int: IntSliderMatplotlibControl,
            float: FloatSliderMatplotlibControl,
            str: (
                PromptMatplotlibControl
                if control.value_range is None
                else StringRadioButtonMatplotlibControl
            ),
        }

        if control_type not in control_class_map:
            logging.warning(
                f"Unsupported control type: {control_type} for control named {name}"
            )
            return None

        control_class = control_class_map[control_type]
        return control_class(name, control, update_func, ax_control)
