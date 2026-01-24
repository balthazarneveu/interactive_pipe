from interactive_pipe.headless.control import Control
from textual.widgets import Switch, Select, Input, Static, ProgressBar
from textual.containers import Horizontal, Vertical
from textual.message import Message
import logging
from functools import partial


class BaseControl:
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
        raise NotImplementedError(
            "This method should be overridden by subclass to check the right slider control type"
        )


class IntSliderTextualControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == int

    def create(self):
        # Textual doesn't have a Slider widget, so we use Input with validation
        # Display current value and allow typing, with min/max validation
        input_widget = Input(
            value=str(self.ctrl.value_default),
            placeholder=f"{self.name} ({self.ctrl.value_range[0]}-{self.ctrl.value_range[1]})",
            name=self.name,
        )

        def validate_and_update(value_str):
            try:
                int_value = int(value_str)
                # Clamp to range
                int_value = max(
                    self.ctrl.value_range[0], min(self.ctrl.value_range[1], int_value)
                )
                self.update_func(self.name, int_value)
                # Update input to show clamped value if it changed
                if int_value != int(value_str):
                    input_widget.value = str(int_value)
            except ValueError:
                # Invalid input, revert to current control value
                input_widget.value = str(self.ctrl.value)

        input_widget._update_func = validate_and_update
        input_widget._ctrl = self.ctrl  # Store reference for reset
        self.control_widget = input_widget
        return input_widget


class FloatSliderTextualControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == float

    def create(self):
        # Textual doesn't have a Slider widget, so we use Input with validation
        # Display current value and allow typing, with min/max validation
        input_widget = Input(
            value=str(self.ctrl.value_default),
            placeholder=f"{self.name} ({self.ctrl.value_range[0]:.3f}-{self.ctrl.value_range[1]:.3f})",
            name=self.name,
        )

        def validate_and_update(value_str):
            try:
                float_value = float(value_str)
                # Clamp to range
                float_value = max(
                    self.ctrl.value_range[0], min(self.ctrl.value_range[1], float_value)
                )
                self.update_func(self.name, float_value)
                # Update input to show clamped value if it changed
                if abs(float_value - float(value_str)) > 1e-6:
                    input_widget.value = str(float_value)
            except ValueError:
                # Invalid input, revert to current control value
                input_widget.value = str(self.ctrl.value)

        input_widget._update_func = validate_and_update
        input_widget._ctrl = self.ctrl  # Store reference for reset
        self.control_widget = input_widget
        return input_widget


class BoolCheckButtonTextualControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == bool

    def create(self):
        switch = Switch(
            value=self.ctrl.value_default,
            name=self.name,
        )
        switch._update_func = lambda val: self.update_func(self.name, val)
        switch._ctrl = self.ctrl  # Store reference for reset
        self.control_widget = switch
        return switch


class StringRadioButtonTextualControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == str
        assert self.ctrl.value_range is not None

    def create(self):
        # Textual Select expects options as (label, value) tuples
        # and value should be just the value (second element), not the tuple
        options = [(item, item) for item in self.ctrl.value_range]
        # Find the default value (second element of tuple)
        default_value = self.ctrl.value_default
        # Ensure default value is in the options
        if default_value not in self.ctrl.value_range:
            default_value = self.ctrl.value_range[0]

        select = Select(
            options=options,
            value=default_value,  # Pass just the value, not the tuple
            name=self.name,
        )

        # Wrap update function - Select.Changed event provides just the value
        def update_wrapper(value):
            # Select.Changed provides the value directly (second element of tuple)
            self.update_func(self.name, value)

        select._update_func = update_wrapper
        select._ctrl = self.ctrl  # Store reference for reset
        self.control_widget = select
        return select


class PromptTextualControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == str
        assert self.ctrl.value_range is None

    def create(self):
        input_widget = Input(
            value=self.ctrl.value if self.ctrl.value else "",
            placeholder=self.name,
            name=self.name,
        )
        input_widget._update_func = lambda val: self.update_func(self.name, val)
        input_widget._ctrl = self.ctrl  # Store reference for reset
        self.control_widget = input_widget
        return input_widget


class ControlFactory:
    @staticmethod
    def create_control(control: Control, update_func):
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
            bool: BoolCheckButtonTextualControl,
            int: IntSliderTextualControl,
            float: FloatSliderTextualControl,
            str: (
                PromptTextualControl
                if control.value_range is None
                else StringRadioButtonTextualControl
            ),
        }

        if control_type not in control_class_map:
            logging.warning(
                f"Unsupported control type: {control_type} for control named {name}"
            )
            return None

        control_class = control_class_map[control_type]
        return control_class(name, control, update_func)
