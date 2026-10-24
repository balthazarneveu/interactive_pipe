import logging

from interactive_pipe.headless.control import Control, RangeControl, range_pair

try:
    import gradio as gr

    GRADIO_AVAILABLE = True
except ImportError:
    GRADIO_AVAILABLE = False
    gr = None
    logging.warning("gradio not available. Gradio controls will not work.")


class BaseControl:
    def __init__(self, name, ctrl: Control, update_func):
        if not GRADIO_AVAILABLE:
            raise ModuleNotFoundError(
                "gradio is required for Gradio controls. Install it with: pip install interactive-pipe[full]"
            )
        super().__init__()
        self.name = name
        self.ctrl = ctrl
        self.update_func = update_func
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
            return RangeTextControl(name, control, update_func)

        control_class_map = {
            bool: TickBoxControl,
            int: IntSliderControl if control.value_range is not None else NumberControl,
            float: FloatSliderControl if control.value_range is not None else NumberControl,
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


class IntSliderControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type is not int:
            raise TypeError(f"Expected int control type, got {self.ctrl._type}")

    def create(self) -> "gr.Slider":  # type: ignore[reportInvalidTypeForm]
        if not GRADIO_AVAILABLE:
            raise ModuleNotFoundError("gradio is required for Gradio controls")
        if gr is None:
            raise ModuleNotFoundError("gradio is required for Gradio controls")
        if self.ctrl.value_range is None:
            raise ValueError("value_range must be set for IntSliderControl")
        value_default = self.ctrl.value_default
        if not isinstance(value_default, (int, float)):
            raise TypeError(f"Expected int or float for IntSliderControl, got {type(value_default)}")
        self.control_widget = gr.Slider(  # type: ignore[reportOptionalMemberAccess]
            value=float(value_default),
            minimum=float(self.ctrl.value_range[0]),  # type: ignore[reportOptionalSubscript]
            maximum=float(self.ctrl.value_range[1]),  # type: ignore[reportOptionalSubscript]
            label=self.name,
            step=self.ctrl.step,
            info=self.ctrl.tooltip,
        )
        return self.control_widget


class FloatSliderControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type is not float:
            raise TypeError(f"Expected float control type, got {self.ctrl._type}")

    def create(self) -> "gr.Slider":  # type: ignore[reportInvalidTypeForm]
        if not GRADIO_AVAILABLE:
            raise ModuleNotFoundError("gradio is required for Gradio controls")
        if gr is None:
            raise ModuleNotFoundError("gradio is required for Gradio controls")
        if self.ctrl.value_range is None:
            raise ValueError("value_range must be set for FloatSliderControl")
        value_default = self.ctrl.value_default
        if not isinstance(value_default, (int, float)):
            raise TypeError(f"Expected int or float for FloatSliderControl, got {type(value_default)}")
        self.control_widget = gr.Slider(  # type: ignore[reportOptionalMemberAccess]
            value=float(value_default),
            minimum=float(self.ctrl.value_range[0]),  # type: ignore[reportOptionalSubscript]
            maximum=float(self.ctrl.value_range[1]),  # type: ignore[reportOptionalSubscript]
            label=self.name,
            step=self.ctrl.step,
            info=self.ctrl.tooltip,
        )

        return self.control_widget


class RangeTextControl(BaseControl):
    """Fallback for RangeControl: Gradio has no built-in two-handle slider.

    A text box holding ``"lo, hi"``; RangeControl parses, sorts and clamps
    it, so the filter still receives a ``(lo, hi)`` tuple.
    """

    def check_control_type(self):
        if not isinstance(self.ctrl, RangeControl):
            raise TypeError(f"Expected a RangeControl, got {type(self.ctrl)}")

    def create(self) -> "gr.Textbox":  # type: ignore[reportInvalidTypeForm]
        if gr is None:
            raise ModuleNotFoundError("gradio is required for Gradio controls")
        value_min, value_max = self.ctrl.value_range  # type: ignore[misc]
        lo, hi = range_pair(self.ctrl)
        info = f"lo, hi within [{value_min}, {value_max}]"
        if self.ctrl.tooltip:
            info = f"{self.ctrl.tooltip} ({info})"
        self.control_widget = gr.Textbox(value=f"{lo}, {hi}", label=self.name, info=info)
        return self.control_widget


class NumberControl(BaseControl):
    """Numeric entry for an int/float control declared without value_range."""

    def check_control_type(self):
        if self.ctrl._type not in (int, float):
            raise TypeError(f"Expected int or float control type, got {self.ctrl._type}")
        if self.ctrl.value_range is not None:
            raise ValueError("value_range must be None for NumberControl")

    def create(self) -> "gr.Number":  # type: ignore[reportInvalidTypeForm]
        if gr is None:
            raise ModuleNotFoundError("gradio is required for Gradio controls")
        value = self.ctrl.value
        if not isinstance(value, (int, float)):
            raise TypeError(f"Expected a number for NumberControl, got {type(value)}")
        self.control_widget = gr.Number(
            value=value,
            label=self.name,
            precision=0 if self.ctrl._type is int else None,
            step=self.ctrl.step if self.ctrl.step else (1 if self.ctrl._type is int else 0.1),
            info=self.ctrl.tooltip,
        )
        return self.control_widget


class TickBoxControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type is not bool:
            raise TypeError(f"Expected bool control type, got {self.ctrl._type}")

    def create(self) -> "gr.Checkbox":  # type: ignore[reportInvalidTypeForm]
        if not GRADIO_AVAILABLE:
            raise ModuleNotFoundError("gradio is required for Gradio controls")
        if gr is None:
            raise ModuleNotFoundError("gradio is required for Gradio controls")
        value = self.ctrl.value
        if not isinstance(value, bool):
            raise TypeError(f"Expected bool for TickBoxControl, got {type(value)}")
        self.control_widget = gr.Checkbox(  # type: ignore[reportOptionalMemberAccess]
            label=self.name, value=value, info=self.ctrl.tooltip
        )
        return self.control_widget

    def reset(self):
        self.control_widget.update(value=self.ctrl.value_default)  # type: ignore[reportAttributeAccessIssue]


class DropdownMenuControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type is not str:
            raise TypeError(f"Expected str control type, got {self.ctrl._type}")
        if not hasattr(self.ctrl, "value_range"):
            raise ValueError("Invalid control type")

    def create(self) -> "gr.Dropdown":  # type: ignore[reportInvalidTypeForm]
        if not GRADIO_AVAILABLE:
            raise ModuleNotFoundError("gradio is required for Gradio controls")
        if gr is None:
            raise ModuleNotFoundError("gradio is required for Gradio controls")
        if self.ctrl.value_range is None:
            raise ValueError("value_range must be set for DropdownMenuControl")
        self.control_widget = gr.Dropdown(  # type: ignore[reportOptionalMemberAccess]
            label=self.name,
            choices=self.ctrl.value_range,
            value=self.ctrl.value,
            info=self.ctrl.tooltip,
        )
        return self.control_widget


class PromptControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type is not str:
            raise TypeError(f"Expected str control type, got {self.ctrl._type}")
        if self.ctrl.value_range is not None:
            raise ValueError("value_range must be None for PromptControl")

    def create(self) -> "gr.Text":  # type: ignore[reportInvalidTypeForm]
        if not GRADIO_AVAILABLE:
            raise ModuleNotFoundError("gradio is required for Gradio controls")
        if gr is None:
            raise ModuleNotFoundError("gradio is required for Gradio controls")
        value = self.ctrl.value
        if not isinstance(value, str):
            raise TypeError(f"Expected str for PromptControl, got {type(value)}")
        self.control_widget = gr.Text(  # type: ignore[reportOptionalMemberAccess]
            label=self.name, value=value, info=self.ctrl.tooltip
        )
        return self.control_widget


class IconButtonsControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type is not str:
            raise TypeError(f"Expected str control type, got {self.ctrl._type}")
        if not hasattr(self.ctrl, "value_range"):
            raise ValueError("Invalid control type")

    def create(self) -> "gr.Radio":  # type: ignore[reportInvalidTypeForm]
        if not GRADIO_AVAILABLE:
            raise ModuleNotFoundError("gradio is required for Gradio controls")
        if gr is None:
            raise ModuleNotFoundError("gradio is required for Gradio controls")
        if self.ctrl.icons is None:
            raise ValueError("icons must be set for IconButtonsControl")
        if self.ctrl.value_range is None:
            raise ValueError("value_range must be set for IconButtonsControl")
        self.control_widget = []
        for idx, icon in enumerate(self.ctrl.icons):  # type: ignore[reportArgumentType]
            # text = self.ctrl.value_range[idx]
            text = ""
            self.control_widget.append(gr.Button(text, icon=self.ctrl.icons[idx]))  # type: ignore[reportOptionalMemberAccess,reportOptionalSubscript]
        return self.control_widget
