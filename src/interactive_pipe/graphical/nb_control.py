from interactive_pipe.headless.control import Control, RangeSliderControlWrapper
import logging

try:
    from ipywidgets import (
        Dropdown,
        FloatSlider,
        IntSlider,
        FloatRangeSlider,
        IntRangeSlider,
        Checkbox,
        Layout,
        Text,
    )

    IPYWIDGETS_AVAILABLE = True
except ImportError:
    IPYWIDGETS_AVAILABLE = False
    # Create dummy classes to allow import even when ipywidgets is not available
    Dropdown = None
    FloatSlider = None
    IntSlider = None
    FloatRangeSlider = None
    IntRangeSlider = None
    Checkbox = None
    Layout = None
    Text = None
    logging.warning("ipywidgets not available. Notebook controls will not work.")


class BaseControl:
    def __init__(self, name, ctrl: Control):
        if not IPYWIDGETS_AVAILABLE:
            raise ModuleNotFoundError(
                "ipywidgets is required for notebook controls. "
                "Install it with: pip install interactive-pipe[notebook]"
            )
        super().__init__()
        self.name = name
        self.ctrl = ctrl
        self.control_widget = None
        self.layout = Layout(width="500px")
        self.check_control_type()

    def create(self):
        raise NotImplementedError("This method should be overridden by subclass")

    def check_control_type(self):
        raise NotImplementedError(
            "This method should be overridden by subclass to check the right slider control type"
        )


class IntSliderNotebookControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type != int:
            raise TypeError(f"Expected int control type, got {self.ctrl._type}")

    def create(self):
        if not IPYWIDGETS_AVAILABLE:
            raise ModuleNotFoundError("ipywidgets is required for notebook controls")
        style = {"description_width": "initial"}
        return IntSlider(
            min=self.ctrl.value_range[0],
            max=self.ctrl.value_range[1],
            value=self.ctrl.value_default,
            style=style,
            layout=self.layout,
        )


class FloatSliderNotebookControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type != float:
            raise TypeError(f"Expected float control type, got {self.ctrl._type}")

    def create(self):
        if not IPYWIDGETS_AVAILABLE:
            raise ModuleNotFoundError("ipywidgets is required for notebook controls")
        style = {"description_width": "initial"}
        return FloatSlider(
            min=self.ctrl.value_range[0],
            max=self.ctrl.value_range[1],
            value=self.ctrl.value_default,
            style=style,
            layout=self.layout,
        )


class BoolCheckButtonNotebookControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type != bool:
            raise TypeError(f"Expected bool control type, got {self.ctrl._type}")

    def create(self):
        if not IPYWIDGETS_AVAILABLE:
            raise ModuleNotFoundError("ipywidgets is required for notebook controls")
        checks = Checkbox(self.ctrl.value_default, layout=self.layout)
        return checks


class DialogNotebookControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type != str:
            raise TypeError(f"Expected str control type, got {self.ctrl._type}")

    def create(self):
        if not IPYWIDGETS_AVAILABLE:
            raise ModuleNotFoundError("ipywidgets is required for notebook controls")
        options = self.ctrl.value_range
        dropdown = Dropdown(options=options, description=self.name, layout=self.layout)
        return dropdown


class PromptNotebookControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type != str:
            raise TypeError(f"Expected str control type, got {self.ctrl._type}")
        if self.ctrl.value_range is not None:
            raise ValueError("value_range must be None for PromptNotebookControl")

    def create(self):
        if not IPYWIDGETS_AVAILABLE:
            raise ModuleNotFoundError("ipywidgets is required for notebook controls")
        text_box = Text(
            value=self.ctrl.value, description=self.name, layout=self.layout
        )
        return text_box


class ControlFactory:
    @staticmethod
    def create_control(control: Control):
        # Check for RangeSliderControlWrapper first
        if isinstance(control, RangeSliderControlWrapper):
            return RangeSliderNotebookControl(control.name, control)

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
            bool: BoolCheckButtonNotebookControl,
            int: IntSliderNotebookControl,
            float: FloatSliderNotebookControl,
            str: (
                PromptNotebookControl
                if control.value_range is None
                else DialogNotebookControl
            ),
        }

        if control_type not in control_class_map:
            logging.warning(
                f"Unsupported control type: {control_type} for control named {name}"
            )
            return None

        control_class = control_class_map[control_type]
        return control_class(name, control)


class RangeSliderNotebookControl(BaseControl):
    """Dual-handle range slider using ipywidgets IntRangeSlider/FloatRangeSlider."""

    def check_control_type(self):
        if not isinstance(self.ctrl, RangeSliderControlWrapper):
            raise TypeError(
                f"Expected RangeSliderControlWrapper, got {type(self.ctrl)}"
            )

    def create(self):
        if not IPYWIDGETS_AVAILABLE:
            raise ModuleNotFoundError("ipywidgets is required for notebook controls")
        range_slider = self.ctrl.range_slider

        # Choose the appropriate slider class based on type
        if range_slider._type == int:
            SliderClass = IntRangeSlider
        else:
            SliderClass = FloatRangeSlider

        style = {"description_width": "initial"}

        def on_change(change):
            # change['new'] is a tuple (left, right)
            left_val, right_val = change["new"][0], change["new"][1]
            # Update both parameters via the wrapper
            self.ctrl.update_both_values(left_val, right_val)

        slider = SliderClass(
            value=range_slider.default,
            min=range_slider.value_range[0],
            max=range_slider.value_range[1],
            description=self.name,
            style=style,
            layout=self.layout,
        )
        slider.observe(on_change, names="value")
        return slider
