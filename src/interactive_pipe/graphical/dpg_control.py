"""Dear PyGui widgets for the interactive_pipe controls.

Mirrors ``qt_control``: a ``ControlFactory`` picks a widget class from the
control type, each widget hands ``update_func(name, value)`` a value expressed
in the control's own domain (float for a float slider, the chosen string for a
dropdown, bool for a tick box) and exposes ``reset()`` to follow the control.

Widgets are created with ``create(parent)`` where ``parent`` is the Dear PyGui
container (table cell, group, window) that should hold them.

The module stays importable without dearpygui: the factory then raises
``ModuleNotFoundError`` when a widget is requested.
"""

import logging
from pathlib import Path
from typing import Any, List, Optional, cast

from interactive_pipe.headless.control import CircularControl, Control, RangeControl, range_pair

try:
    from interactive_pipe.graphical.dpg_backend import INSTALL_HINT, dpg

    DPG_AVAILABLE = True
except ModuleNotFoundError:
    dpg = cast(Any, None)  # every widget path checks DPG_AVAILABLE first
    INSTALL_HINT = "pip install 'interactive-pipe[dpg]'"
    DPG_AVAILABLE = False

SELECTED_ICON_BACKGROUND = (70, 130, 180, 255)
UNSELECTED_ICON_BACKGROUND = (0, 0, 0, 0)
ICON_SIZE = 64


class BaseControl:
    """Dear PyGui widget wrapper for one Control.

    ``create(parent)`` builds the widget inside ``parent`` and returns its
    item id; ``widgets`` lists every item that takes keyboard focus (text
    entry fields) so the window can mute global shortcuts while typing.
    """

    def __init__(self, name: str, ctrl: Control, update_func, texture_registry=None):
        if not DPG_AVAILABLE:
            raise ModuleNotFoundError(f"Dear PyGui is required for dpg controls. Install it with: {INSTALL_HINT}")
        self.name = name
        self.ctrl = ctrl
        self.update_func = update_func
        self.texture_registry = texture_registry
        self.control_widget: Any = None
        self.widgets: List[Any] = []
        self.check_control_type()

    def create(self, parent):
        raise NotImplementedError("This method should be overridden by subclass")

    def check_control_type(self):
        raise NotImplementedError("This method should be overridden by subclass to check the right control type")

    def reset(self):
        raise NotImplementedError("This method should be overridden by subclass")

    def _add_tooltip(self, item):
        if self.ctrl.tooltip and item is not None:
            dpg.add_text(self.ctrl.tooltip, parent=dpg.add_tooltip(item))

    def _emit(self, value):
        self.update_func(self.name, value)


class ControlFactory:
    """Pick the widget class for a control (same rules as the Qt factory)."""

    def __init__(self, texture_registry=None):
        self.texture_registry = texture_registry

    def create_control(self, control: Control, update_func) -> Optional[BaseControl]:
        control_type = control._type
        name = control.name
        # single-choice dropdowns have nothing to show
        if control_type is str and control.value_range is not None and len(control.value_range) == 1:
            return None
        if isinstance(control, RangeControl):
            control_class = RangeSliderControl
        elif control_type is bool:
            control_class = TickBoxControl
        elif control_type in (int, float):
            if control.value_range is None:
                control_class = IntInputControl if control_type is int else FloatInputControl
            elif isinstance(control, CircularControl):
                control_class = KnobControl
            else:
                control_class = IntSliderControl if control_type is int else FloatSliderControl
        elif control_type is str:
            if control.value_range is None:
                control_class = PromptControl
            elif control.icons is None:
                control_class = DropdownMenuControl
            else:
                control_class = IconButtonsControl
        else:
            logging.warning(f"Unsupported control type: {control_type} for control named {name}")
            return None
        return control_class(name, control, update_func, texture_registry=self.texture_registry)


def _snap(value, value_min, step):
    """Snap a slider value onto the control's step grid."""
    if not step:
        return value
    return value_min + round((value - value_min) / step) * step


class IntSliderControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type is not int:
            raise TypeError(f"Expected int control type, got {self.ctrl._type}")
        if self.ctrl.value_range is None:
            raise ValueError("value_range must be set for IntSliderControl")

    def create(self, parent):
        value_min, value_max = self.ctrl.value_range  # type: ignore[misc]
        if not isinstance(value_min, int) or not isinstance(value_max, int):
            raise TypeError(f"Expected int for IntSliderControl range, got {type(value_min)}, {type(value_max)}")
        self.control_widget = dpg.add_slider_int(
            parent=parent,
            default_value=int(self.ctrl.value),
            min_value=value_min,
            max_value=value_max,
            clamped=True,
            width=-1,
            callback=self._on_change,
        )
        self._add_tooltip(self.control_widget)
        return self.control_widget

    def _on_change(self, _sender, app_data, _user_data):
        step = self.ctrl.step if isinstance(self.ctrl.step, int) and self.ctrl.step > 1 else 1
        snapped = int(_snap(int(app_data), self.ctrl.value_range[0], step))  # type: ignore[index]
        if snapped != app_data:
            dpg.set_value(self.control_widget, snapped)
        self._emit(snapped)

    def reset(self):
        dpg.set_value(self.control_widget, int(self.ctrl.value))


class FloatSliderControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type is not float:
            raise TypeError(f"Expected float control type, got {self.ctrl._type}")
        if self.ctrl.value_range is None:
            raise ValueError("value_range must be set for FloatSliderControl")

    def create(self, parent):
        value_min, value_max = self.ctrl.value_range  # type: ignore[misc]
        self.control_widget = dpg.add_slider_float(
            parent=parent,
            default_value=float(self.ctrl.value),
            min_value=float(value_min),
            max_value=float(value_max),
            clamped=True,
            width=-1,
            format="%.4g",
            callback=self._on_change,
        )
        self._add_tooltip(self.control_widget)
        return self.control_widget

    def _on_change(self, _sender, app_data, _user_data):
        value_min, value_max = self.ctrl.value_range  # type: ignore[misc]
        snapped = _snap(float(app_data), float(value_min), self.ctrl.step)
        snapped = float(min(max(snapped, value_min), value_max))
        if snapped != app_data:
            dpg.set_value(self.control_widget, snapped)
        self._emit(snapped)

    def reset(self):
        dpg.set_value(self.control_widget, float(self.ctrl.value))


class RangeSliderControl(BaseControl):
    """Single-track two-handle slider for a RangeControl, drawn on a drawlist.

    Dear PyGui has no range slider, so the track and handles are drawn by hand
    and driven by mouse handlers (grab the nearest handle, drag, release).
    The drawlist is re-laid out to the available width whenever the cell is
    resized. Dragging one handle past the other pushes it along so
    ``lo <= hi`` always holds; ``update_func`` receives the ``(lo, hi)`` tuple.
    """

    HEIGHT = 26
    MARGIN = 10  # handle radius + 1
    GROOVE = (90, 90, 96, 255)
    FILL = (66, 150, 250, 255)
    HANDLE = (230, 230, 235, 255)
    HANDLE_ACTIVE = (255, 255, 255, 255)

    def check_control_type(self):
        if not isinstance(self.ctrl, RangeControl):
            raise TypeError(f"Expected a RangeControl, got {type(self.ctrl)}")

    def _cast(self, value):
        return int(value) if self.ctrl._type is int else float(value)

    def _snapped(self, value):
        value_min, value_max = self.ctrl.value_range  # type: ignore[misc]
        snapped = _snap(value, value_min, self.ctrl.step)
        snapped = self._cast(min(max(snapped, value_min), value_max))
        return snapped if self.ctrl._type is int else round(snapped, 12)

    def create(self, parent):
        self.lo, self.hi = (self._cast(v) for v in range_pair(self.ctrl))
        self._width = 300
        self._drag = None  # "lo" / "hi" while a handle is held
        self._last_handle = "hi"
        self.control_widget = dpg.add_child_window(
            parent=parent, width=-1, height=self.HEIGHT, border=False, no_scrollbar=True
        )
        self.drawlist = dpg.add_drawlist(width=self._width, height=self.HEIGHT, parent=self.control_widget)
        self._handlers = dpg.add_item_handler_registry()
        dpg.add_item_resize_handler(callback=self._on_resize, parent=self._handlers)
        dpg.bind_item_handler_registry(self.control_widget, self._handlers)
        self._mouse = dpg.add_handler_registry()
        dpg.add_mouse_down_handler(button=dpg.mvMouseButton_Left, callback=self._on_mouse_down, parent=self._mouse)
        dpg.add_mouse_release_handler(
            button=dpg.mvMouseButton_Left, callback=self._on_mouse_release, parent=self._mouse
        )
        self._add_tooltip(self.control_widget)
        self._redraw()
        return self.control_widget

    # -- geometry -----------------------------------------------------------
    def _bounds(self):
        value_min, value_max = self.ctrl.value_range  # type: ignore[misc]
        return float(value_min), float(value_max)

    def _x_of(self, value) -> float:
        value_min, value_max = self._bounds()
        usable = max(1.0, self._width - 2 * self.MARGIN)
        return self.MARGIN + usable * (value - value_min) / (value_max - value_min)

    def _value_at(self, x: float):
        value_min, value_max = self._bounds()
        usable = max(1.0, self._width - 2 * self.MARGIN)
        fraction = min(max((x - self.MARGIN) / usable, 0.0), 1.0)
        return self._snapped(value_min + fraction * (value_max - value_min))

    def _redraw(self):
        dpg.delete_item(self.drawlist, children_only=True)
        cy = self.HEIGHT / 2
        x_lo, x_hi = self._x_of(self.lo), self._x_of(self.hi)
        value_min, value_max = self.ctrl.value_range  # type: ignore[misc]
        dpg.draw_line(
            (self._x_of(value_min), cy),
            (self._x_of(value_max), cy),
            color=self.GROOVE,
            thickness=4,
            parent=self.drawlist,
        )
        dpg.draw_line((x_lo, cy), (x_hi, cy), color=self.FILL, thickness=4, parent=self.drawlist)
        for which, x in (("lo", x_lo), ("hi", x_hi)):
            held = self._drag == which
            dpg.draw_circle(
                (x, cy),
                self.MARGIN - 2,
                color=self.FILL,
                fill=self.HANDLE_ACTIVE if held else self.HANDLE,
                thickness=2,
                parent=self.drawlist,
            )

    def _on_resize(self, _sender=None, _app_data=None, _user_data=None):
        width = int(dpg.get_item_rect_size(self.control_widget)[0]) - 4
        if width > 4 * self.MARGIN and width != self._width:
            self._width = width
            dpg.configure_item(self.drawlist, width=width)
            self._redraw()

    # -- interaction (local x = pixels from the left edge of the track) -----
    def _local_x(self) -> float:
        return dpg.get_mouse_pos(local=False)[0] - dpg.get_item_rect_min(self.drawlist)[0]

    def _on_mouse_down(self, _sender=None, _app_data=None, _user_data=None):
        if self._drag is None:
            if not dpg.is_item_hovered(self.control_widget):
                return
            self._press(self._local_x())
        else:
            self._move(self._drag, self._value_at(self._local_x()))

    def _on_mouse_release(self, _sender=None, _app_data=None, _user_data=None):
        self._release()

    def _press(self, x: float):
        d_lo, d_hi = abs(x - self._x_of(self.lo)), abs(x - self._x_of(self.hi))
        if d_lo == d_hi:  # stacked handles: pick the one that can move toward the click
            which = "lo" if x < self._x_of(self.lo) else "hi"
        else:
            which = "lo" if d_lo < d_hi else "hi"
        self._drag = which
        self._move(which, self._value_at(x))

    def _release(self):
        if self._drag is not None:
            self._last_handle = self._drag
            self._drag = None
            self._redraw()

    def _move(self, which: str, value):
        lo, hi = self.lo, self.hi
        if which == "lo":
            lo, hi = value, max(hi, value)
        else:
            lo, hi = min(lo, value), value
        if (lo, hi) != (self.lo, self.hi):
            self.lo, self.hi = lo, hi
            self._emit((lo, hi))
        self._redraw()

    def reset(self):
        self.lo, self.hi = (self._cast(v) for v in range_pair(self.ctrl))
        self._redraw()


class KnobControl(BaseControl):
    """Rotary knob for CircularControl (int or float with a value_range)."""

    def check_control_type(self):
        if self.ctrl._type not in (int, float):
            raise TypeError(f"Expected numeric control type, got {self.ctrl._type}")
        if self.ctrl.value_range is None:
            raise ValueError("value_range must be set for KnobControl")

    def create(self, parent):
        value_min, value_max = self.ctrl.value_range  # type: ignore[misc]
        self.control_widget = dpg.add_knob_float(
            parent=parent,
            default_value=float(self.ctrl.value),
            min_value=float(value_min),
            max_value=float(value_max),
            callback=self._on_change,
        )
        self._add_tooltip(self.control_widget)
        return self.control_widget

    def _on_change(self, _sender, app_data, _user_data):
        value_min, value_max = self.ctrl.value_range  # type: ignore[misc]
        value = _snap(float(app_data), float(value_min), self.ctrl.step)
        value = min(max(value, value_min), value_max)
        if self.ctrl._type is int:
            value = int(round(float(value)))
        self._emit(value)

    def reset(self):
        dpg.set_value(self.control_widget, float(self.ctrl.value))


class _InputControl(BaseControl):
    """Numeric entry (with +/- buttons) for a control declared without value_range."""

    def check_control_type(self):
        if self.ctrl.value_range is not None:
            raise ValueError(f"{type(self).__name__} is meant for controls without value_range")

    def _add_input(self, parent):
        raise NotImplementedError

    def create(self, parent):
        self.control_widget = self._add_input(parent)
        self.widgets = [self.control_widget]
        self._add_tooltip(self.control_widget)
        return self.control_widget

    def _on_change(self, _sender, app_data, _user_data):
        self._emit(self.ctrl._type(app_data))  # type: ignore[misc]

    def reset(self):
        dpg.set_value(self.control_widget, self.ctrl.value)


class IntInputControl(_InputControl):
    def check_control_type(self):
        if self.ctrl._type is not int:
            raise TypeError(f"Expected int control type, got {self.ctrl._type}")
        super().check_control_type()

    def _add_input(self, parent):
        step = self.ctrl.step if isinstance(self.ctrl.step, int) and self.ctrl.step else 1
        return dpg.add_input_int(
            parent=parent,
            default_value=int(self.ctrl.value),
            step=step,
            step_fast=10 * step,
            width=-1,
            callback=self._on_change,
        )


class FloatInputControl(_InputControl):
    def check_control_type(self):
        if self.ctrl._type is not float:
            raise TypeError(f"Expected float control type, got {self.ctrl._type}")
        super().check_control_type()

    def _add_input(self, parent):
        step = float(self.ctrl.step) if self.ctrl.step else 0.1
        return dpg.add_input_float(
            parent=parent,
            default_value=float(self.ctrl.value),
            step=step,
            step_fast=10 * step,
            format="%.4f",
            width=-1,
            callback=self._on_change,
        )


class TickBoxControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type is not bool:
            raise TypeError(f"Expected bool control type, got {self.ctrl._type}")

    def create(self, parent):
        self.control_widget = dpg.add_checkbox(
            parent=parent,
            default_value=bool(self.ctrl.value),
            callback=lambda _sender, app_data, _user_data: self._emit(bool(app_data)),
        )
        self._add_tooltip(self.control_widget)
        return self.control_widget

    def reset(self):
        dpg.set_value(self.control_widget, bool(self.ctrl.value))


class DropdownMenuControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type is not str:
            raise TypeError(f"Expected str control type, got {self.ctrl._type}")
        if self.ctrl.value_range is None:
            raise ValueError("value_range must be set for DropdownMenuControl")

    def create(self, parent):
        items = [str(item) for item in self.ctrl.value_range]  # type: ignore[union-attr]
        self.control_widget = dpg.add_combo(
            items,
            parent=parent,
            default_value=str(self.ctrl.value),
            width=-1,
            callback=lambda _sender, app_data, _user_data: self._emit(app_data),
        )
        self._add_tooltip(self.control_widget)
        return self.control_widget

    def reset(self):
        dpg.set_value(self.control_widget, str(self.ctrl.value))


class PromptControl(BaseControl):
    def check_control_type(self):
        if self.ctrl._type is not str:
            raise TypeError(f"Expected str control type, got {self.ctrl._type}")
        if self.ctrl.value_range is not None:
            raise ValueError("value_range must be None for PromptControl")

    def create(self, parent):
        self.control_widget = dpg.add_input_text(
            parent=parent,
            default_value=str(self.ctrl.value),
            width=-1,
            callback=lambda _sender, app_data, _user_data: self._emit(app_data),
        )
        self.widgets = [self.control_widget]
        self._add_tooltip(self.control_widget)
        return self.control_widget

    def reset(self):
        dpg.set_value(self.control_widget, str(self.ctrl.value))


class IconButtonsControl(BaseControl):
    """One image button per choice; the selected one gets a colored background."""

    def check_control_type(self):
        if self.ctrl._type is not str:
            raise TypeError(f"Expected str control type, got {self.ctrl._type}")
        if self.ctrl.value_range is None or self.ctrl.icons is None:
            raise ValueError("Invalid control type or missing value range for icons bar creation.")

    def create(self, parent):
        if self.texture_registry is None:
            self.texture_registry = dpg.add_texture_registry()
        self.control_widgets: List[Any] = []
        self.texture_tags: List[Any] = []
        self.choices: List[str] = []
        group = dpg.add_group(horizontal=True, parent=parent)
        for choice, icon_path in zip(self.ctrl.value_range, self.ctrl.icons):  # type: ignore[arg-type]
            loaded = dpg.load_image(str(Path(icon_path)))
            if loaded is None:  # Dear PyGui returns None for a missing or unreadable image
                raise FileNotFoundError(f"Could not load icon {icon_path!s} for control {self.name!r}")
            width, height, _channels, data = loaded
            texture = dpg.add_static_texture(
                width=width, height=height, default_value=data, parent=self.texture_registry
            )
            button = dpg.add_image_button(
                texture,
                parent=group,
                width=ICON_SIZE,
                height=ICON_SIZE,
                background_color=UNSELECTED_ICON_BACKGROUND,
                callback=self._on_click,
                user_data=choice,
            )
            dpg.add_text(self.ctrl.tooltip or str(choice), parent=dpg.add_tooltip(button))
            self.texture_tags.append(texture)
            self.control_widgets.append(button)
            self.choices.append(choice)
        self.control_widget = group
        self.reset()
        return group

    def _on_click(self, _sender, _app_data, user_data):
        self._check_only(user_data)
        self._emit(user_data)

    def _check_only(self, choice):
        self._selected = None
        for button, button_choice in zip(self.control_widgets, self.choices):
            selected = button_choice == choice
            if selected:
                self._selected = button_choice
            dpg.configure_item(
                button, background_color=SELECTED_ICON_BACKGROUND if selected else UNSELECTED_ICON_BACKGROUND
            )

    def selected_choice(self) -> Optional[str]:
        """Choice whose button is highlighted (None when nothing is selected)."""
        return getattr(self, "_selected", None)

    def reset(self):
        self._check_only(self.ctrl.value)
