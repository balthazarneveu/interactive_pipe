
from functools import partial
from interactive_pipe.headless.control import Control
import logging
import gradio as gr


class BaseControl():
    def __init__(self, name, ctrl: Control, update_func):
        super().__init__()
        self.name = name
        self.ctrl = ctrl
        self.update_func = update_func
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
            str: DropdownMenuControl
        }

        if control_type not in control_class_map:
            logging.warning(
                f"Unsupported control type: {control_type} for control named {name}")
            return None

        control_class = control_class_map[control_type]
        return control_class(name, control, update_func)


class IntSliderControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == int

    def create(self) -> gr.Slider:
        self.control_widget = gr.Slider(
            value=self.ctrl.value_default,
            minimum=self.ctrl.value_range[0],
            maximum=self.ctrl.value_range[1],
            label=self.name,
            step=1
        )
        return self.control_widget


class FloatSliderControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == float

    def create(self) -> gr.Slider:
        self.control_widget = gr.Slider(
            value=self.ctrl.value_default,
            minimum=self.ctrl.value_range[0],
            maximum=self.ctrl.value_range[1],
            label=self.name,
        )

        return self.control_widget


class TickBoxControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == bool

    def create(self) -> gr.Checkbox:
        self.control_widget = gr.Checkbox(label=self.name, value=self.ctrl.value)
        return self.control_widget

    def reset(self):
        self.control_widget.update(value=self.ctrl.default_value)


class DropdownMenuControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == str
        if not hasattr(self.ctrl, 'value_range'):
            raise ValueError("Invalid control type")

    def create(self) -> gr.Dropdown:
        # Create a horizontal layout to hold the dropdown menu
        self.control_widget = gr.Dropdown(label=self.name, choices=self.ctrl.value_range, value=self.ctrl.value)
        return self.control_widget

    def reset(self):
        index = self.control_widget.findText(self.ctrl.value)
        if index >= 0:
            self.control_widget.setCurrentIndex(index)
        self.control_widget.setCurrentIndex(index)
