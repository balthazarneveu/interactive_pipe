from ipywidgets import Dropdown, FloatSlider, IntSlider, Checkbox, Layout
from interactive_pipe.headless.control import Control
import logging


class BaseControl:
    layout = Layout(width='500px')

    def __init__(self, name, ctrl: Control):
        super().__init__()
        self.name = name
        self.ctrl = ctrl
        self.control_widget = None
        self.check_control_type()

    def create(self):
        raise NotImplementedError(
            "This method should be overridden by subclass")

    def check_control_type(self):
        raise NotImplementedError(
            "This method should be overridden by subclass to check the right slider control type")


class IntSliderNotebookControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == int

    def create(self):
        style = {'description_width': 'initial'}
        return IntSlider(min=self.ctrl.value_range[0], max=self.ctrl.value_range[1], value=self.ctrl.value_default, style=style, layout=self.layout)


class FloatSliderNotebookControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == float

    def create(self):
        style = {'description_width': 'initial'}
        return FloatSlider(min=self.ctrl.value_range[0], max=self.ctrl.value_range[1], value=self.ctrl.value_default, style=style, layout=self.layout)


class BoolCheckButtonNotebookControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == bool

    def create(self):
        checks = Checkbox(self.ctrl.value_default, layout=self.layout)
        return checks


class DialogNotebookControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == str

    def create(self):
        options = self.ctrl.value_range
        radio = Dropdown(
            options=options, description=self.name, layout=self.layout)
        return radio


class ControlFactory:
    @staticmethod
    def create_control(control: Control):
        control_type = control._type
        name = control.name
        control_class_map = {
            bool: BoolCheckButtonNotebookControl,
            int: IntSliderNotebookControl,
            float: FloatSliderNotebookControl,
            str: DialogNotebookControl,
        }

        if control_type not in control_class_map:
            logging.warning(
                f"Unsupported control type: {control_type} for control named {name}")
            return None

        control_class = control_class_map[control_type]
        return control_class(name, control)
