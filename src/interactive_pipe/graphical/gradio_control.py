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
            return RangeSliderControl(name, control, update_func)

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


_RANGE_CSS = """
.ip-range { padding: 4px 2px 8px; font-family: var(--font, sans-serif); }
.ip-range .ip-head { display: flex; justify-content: space-between; font-size: var(--text-sm, 13px);
  color: var(--body-text-color, #333); margin-bottom: 6px; }
.ip-range .ip-name { font-weight: 600; }
.ip-range .ip-track { position: relative; height: 22px; }
.ip-range .ip-groove, .ip-range .ip-fill { position: absolute; top: 9px; height: 4px; border-radius: 2px; }
.ip-range .ip-groove { left: 0; right: 0; background: var(--neutral-300, #d4d4d8); }
.ip-range .ip-fill { background: var(--color-accent, #f97316); }
.ip-range input[type=range] { position: absolute; left: 0; top: 0; width: 100%; height: 22px; margin: 0;
  background: none; pointer-events: none; -webkit-appearance: none; appearance: none; }
.ip-range input[type=range]::-webkit-slider-runnable-track { background: none; height: 22px; }
.ip-range input[type=range]::-moz-range-track { background: none; }
.ip-range input[type=range]::-webkit-slider-thumb { pointer-events: auto; -webkit-appearance: none; width: 16px;
  height: 16px; margin-top: 3px; border-radius: 50%; background: #fff; border: 2px solid var(--color-accent, #f97316);
  cursor: grab; }
.ip-range input[type=range]::-moz-range-thumb { pointer-events: auto; width: 12px; height: 12px; border-radius: 50%;
  background: #fff; border: 2px solid var(--color-accent, #f97316); cursor: grab; }
"""

_RANGE_HTML = """
<div class="ip-range">
  <div class="ip-head"><span class="ip-name">${label}</span><span class="ip-readout"></span></div>
  <div class="ip-track">
    <div class="ip-groove"></div><div class="ip-fill"></div>
    <input class="ip-lo" type="range" min="${vmin}" max="${vmax}" step="${step}">
    <input class="ip-hi" type="range" min="${vmin}" max="${vmax}" step="${step}">
  </div>
</div>
"""

_RANGE_JS = """
const lo = element.querySelector('.ip-lo'), hi = element.querySelector('.ip-hi');
const fill = element.querySelector('.ip-fill'), readout = element.querySelector('.ip-readout');
const vmin = parseFloat(lo.min), vmax = parseFloat(lo.max);
const decimals = (String(lo.step).split('.')[1] || '').length;
const fmt = (v) => Number(v).toFixed(decimals);
function draw(a, b) {
  lo.value = a; hi.value = b;
  fill.style.left = (100 * (a - vmin) / (vmax - vmin)) + '%';
  fill.style.width = (100 * (b - a) / (vmax - vmin)) + '%';
  readout.textContent = fmt(a) + ' \u2013 ' + fmt(b);
}
function current() { return props.value || [vmin, vmax]; }
draw(...current());
function commit(a, b) { props.value = [a, b]; trigger('change'); }
lo.addEventListener('input', () => {
  let a = parseFloat(lo.value), b = parseFloat(hi.value);
  if (a > b) b = a;
  draw(a, b);
});
hi.addEventListener('input', () => {
  let a = parseFloat(lo.value), b = parseFloat(hi.value);
  if (b < a) a = b;
  draw(a, b);
});
for (const input of [lo, hi]) {
  input.addEventListener('change', () => commit(parseFloat(lo.value), parseFloat(hi.value)));
}
// thumbs overlap at the ends: keep the one that can still move on top
lo.addEventListener('pointerdown', () => { lo.style.zIndex = 2; hi.style.zIndex = 1; });
hi.addEventListener('pointerdown', () => { hi.style.zIndex = 2; lo.style.zIndex = 1; });
"""


class RangeSliderControl(BaseControl):
    """Two-handle range slider for a RangeControl, drawn as a ``gr.HTML`` component.

    Gradio has no built-in range slider, so this is two overlaid native
    ``<input type=range>`` on a shared track. The component value is the
    ``[lo, hi]`` list (RangeControl sorts and clamps it) and it fires
    ``change`` when a handle is released, like ``gr.Slider``.
    """

    def check_control_type(self):
        if not isinstance(self.ctrl, RangeControl):
            raise TypeError(f"Expected a RangeControl, got {type(self.ctrl)}")

    def create(self) -> "gr.HTML":  # type: ignore[reportInvalidTypeForm]
        if gr is None:
            raise ModuleNotFoundError("gradio is required for Gradio controls")
        value_min, value_max = self.ctrl.value_range  # type: ignore[misc]
        lo, hi = range_pair(self.ctrl)
        template = (
            _RANGE_HTML.replace("${label}", str(self.name))
            .replace("${vmin}", str(value_min))
            .replace("${vmax}", str(value_max))
            .replace("${step}", str(self.ctrl.step))
        )
        self.control_widget = gr.HTML(
            value=[lo, hi],
            html_template=template,
            css_template=_RANGE_CSS,
            js_on_load=_RANGE_JS,
            elem_classes=["ip-range-control"],
        )
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
