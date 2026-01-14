from interactive_pipe.headless.control import Control
import logging

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
                "gradio is required for Gradio controls. "
                "Install it with: pip install interactive-pipe[full]"
            )
        super().__init__()
        self.name = name
        self.ctrl = ctrl
        self.update_func = update_func
        self.check_control_type()

    def create(self):
        raise NotImplementedError("This method should be overridden by subclass")

    def check_control_type(self):
        raise NotImplementedError(
            "This method should be overridden by subclass to check the right slider control type"
        )


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
            bool: TickBoxControl,
            int: IntSliderControl,
            float: FloatSliderControl,
            str: (
                PromptControl
                if control.value_range is None
                else (
                    DropdownMenuControl if control.icons is None else IconButtonsControl
                )
            ),
        }

        if control_type not in control_class_map:
            logging.warning(
                f"Unsupported control type: {control_type} for control named {name}"
            )
            return None

        control_class = control_class_map[control_type]
        return control_class(name, control, update_func)


class IntSliderControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type != int:
            raise TypeError(f"Expected int control type, got {self.ctrl._type}")

    def create(self) -> "gr.Slider":
        if not GRADIO_AVAILABLE:
            raise ModuleNotFoundError("gradio is required for Gradio controls")
        self.control_widget = gr.Slider(
            value=self.ctrl.value_default,
            minimum=self.ctrl.value_range[0],
            maximum=self.ctrl.value_range[1],
            label=self.name,
            step=1,
        )
        return self.control_widget


class FloatSliderControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type != float:
            raise TypeError(f"Expected float control type, got {self.ctrl._type}")

    def create(self) -> "gr.Slider":
        if not GRADIO_AVAILABLE:
            raise ModuleNotFoundError("gradio is required for Gradio controls")
        self.control_widget = gr.Slider(
            value=self.ctrl.value_default,
            minimum=self.ctrl.value_range[0],
            maximum=self.ctrl.value_range[1],
            label=self.name,
        )

        return self.control_widget


class TickBoxControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type != bool:
            raise TypeError(f"Expected bool control type, got {self.ctrl._type}")

    def create(self) -> "gr.Checkbox":
        if not GRADIO_AVAILABLE:
            raise ModuleNotFoundError("gradio is required for Gradio controls")
        self.control_widget = gr.Checkbox(label=self.name, value=self.ctrl.value)
        return self.control_widget

    def reset(self):
        self.control_widget.update(value=self.ctrl.default_value)


class DropdownMenuControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type != str:
            raise TypeError(f"Expected str control type, got {self.ctrl._type}")
        if not hasattr(self.ctrl, "value_range"):
            raise ValueError("Invalid control type")

    def create(self) -> "gr.Dropdown":
        if not GRADIO_AVAILABLE:
            raise ModuleNotFoundError("gradio is required for Gradio controls")
        self.control_widget = gr.Dropdown(
            label=self.name, choices=self.ctrl.value_range, value=self.ctrl.value
        )
        return self.control_widget


class PromptControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type != str:
            raise TypeError(f"Expected str control type, got {self.ctrl._type}")
        if self.ctrl.value_range is not None:
            raise ValueError("value_range must be None for PromptControl")

    def create(self) -> "gr.Text":
        if not GRADIO_AVAILABLE:
            raise ModuleNotFoundError("gradio is required for Gradio controls")
        self.control_widget = gr.Text(label=self.name, value=self.ctrl.value)
        return self.control_widget


class IconButtonsControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type != str:
            raise TypeError(f"Expected str control type, got {self.ctrl._type}")
        if not hasattr(self.ctrl, "value_range"):
            raise ValueError("Invalid control type")

    def create(self) -> "gr.Radio":
        if not GRADIO_AVAILABLE:
            raise ModuleNotFoundError("gradio is required for Gradio controls")
        self.control_widget = []
        for idx, icon in enumerate(self.ctrl.icons):
            # text = self.ctrl.value_range[idx]
            text = ""
            self.control_widget.append(gr.Button(text, icon=self.ctrl.icons[idx]))
        return self.control_widget
