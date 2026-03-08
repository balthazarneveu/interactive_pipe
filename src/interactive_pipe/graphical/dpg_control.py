import logging
from pathlib import Path

from interactive_pipe.headless.control import Control

DPG_AVAILABLE = False

try:
    import dearpygui.dearpygui as dpg

    DPG_AVAILABLE = True
except ImportError:
    dpg = None  # type: ignore[reportAssignmentType]
    logging.warning("DearPyGui not available. DPG controls will not work.")


class BaseControl:
    """Base class for all DPG controls."""

    def __init__(self, name, ctrl: Control, update_func, silent=False):
        if not DPG_AVAILABLE:
            raise ModuleNotFoundError(
                "DearPyGui is required for DPG controls. Install it with: pip install interactive-pipe[dpg]"
            )
        self.name = name
        self.ctrl = ctrl
        self.update_func = update_func
        self.control_widget = None
        self.silent = silent
        self.check_control_type()

    def create(self, parent):
        """Create and return the DPG widget tag."""
        raise NotImplementedError("This method should be overridden by subclass")

    def check_control_type(self):
        """Check if the control type matches the expected type."""
        raise NotImplementedError("This method should be overridden by subclass to check the right slider control type")

    def reset(self):
        """Reset control to default value."""
        raise NotImplementedError("This method should be overridden by subclass")


class ControlFactory:
    """Factory for creating DPG control widgets."""

    @staticmethod
    def create_control(control: Control, update_func):
        """Create appropriate control based on control type.

        Args:
            control: Control instance from interactive_pipe
            update_func: Callback function for value updates

        Returns:
            Control instance or None if control should not be displayed
        """
        control_type = control._type
        name = control.name

        # Return None for single-value controls (don't show anything)
        if control_type is str and control.value_range is not None and len(control.value_range) == 1:
            return None

        control_class_map = {
            bool: TickBoxControl,
            int: IntSliderControl,
            float: FloatSliderControl,
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
    """Integer slider control using dpg.add_slider_int()."""

    def check_control_type(self):
        if self.ctrl._type is not int:
            raise TypeError(f"Expected int control type, got {self.ctrl._type}")

    def create(self, parent):
        assert dpg is not None
        if self.ctrl.value_range is None:
            raise ValueError("value_range must be set for IntSliderControl")

        valmin = self.ctrl.value_range[0]
        valmax = self.ctrl.value_range[1]
        valdefault = self.ctrl.value_default

        if not isinstance(valmin, int) or not isinstance(valmax, int):
            raise TypeError(f"Expected int for IntSliderControl range, got {type(valmin)}, {type(valmax)}")
        if not isinstance(valdefault, int):
            raise TypeError(f"Expected int for IntSliderControl default, got {type(valdefault)}")

        # DPG callback signature: (sender, app_data, user_data)
        user_data = (self.name, self.update_func)

        def int_slider_callback(sender, app_data, user_data):
            name, update_func = user_data
            logging.debug(f"DPG IntSlider callback: name={name}, value={app_data}")
            update_func(name, app_data)

        tag = f"{self.name}_slider"
        self.control_widget = dpg.add_slider_int(
            label="",
            default_value=valdefault,
            min_value=valmin,
            max_value=valmax,
            callback=int_slider_callback,
            user_data=user_data,
            parent=parent,
            tag=tag,
            width=-1,
        )

        if self.ctrl.tooltip:
            with dpg.tooltip(self.control_widget):
                dpg.add_text(self.ctrl.tooltip)

        return self.control_widget

    def reset(self):
        assert dpg is not None
        value = self.ctrl.value
        if not isinstance(value, int):
            raise TypeError(f"Expected int for IntSliderControl value, got {type(value)}")
        dpg.set_value(self.control_widget, value)


class FloatSliderControl(BaseControl):
    """Float slider control using dpg.add_slider_float()."""

    def check_control_type(self):
        if self.ctrl._type is not float:
            raise TypeError(f"Expected float control type, got {self.ctrl._type}")

    def create(self, parent):
        assert dpg is not None
        if self.ctrl.value_range is None:
            raise ValueError("value_range must be set for FloatSliderControl")

        valmin = self.ctrl.value_range[0]
        valmax = self.ctrl.value_range[1]
        valdefault = self.ctrl.value_default

        if not isinstance(valdefault, (int, float)):
            raise TypeError(f"Expected float for FloatSliderControl default, got {type(valdefault)}")

        # DPG callback signature: (sender, app_data, user_data)
        user_data = (self.name, self.update_func)

        def float_slider_callback(sender, app_data, user_data):
            name, update_func = user_data
            logging.debug(f"DPG FloatSlider callback: name={name}, value={app_data}")
            update_func(name, app_data)

        tag = f"{self.name}_slider"
        self.control_widget = dpg.add_slider_float(
            label="",
            default_value=float(valdefault),
            min_value=float(valmin),
            max_value=float(valmax),
            callback=float_slider_callback,
            user_data=user_data,
            parent=parent,
            tag=tag,
            width=-1,
        )

        if self.ctrl.tooltip:
            with dpg.tooltip(self.control_widget):
                dpg.add_text(self.ctrl.tooltip)

        return self.control_widget

    def reset(self):
        assert dpg is not None
        value = self.ctrl.value
        if not isinstance(value, (int, float)):
            raise TypeError(f"Expected float for FloatSliderControl value, got {type(value)}")
        dpg.set_value(self.control_widget, float(value))


class TickBoxControl(BaseControl):
    """Boolean checkbox control using dpg.add_checkbox()."""

    def check_control_type(self):
        if self.ctrl._type is not bool:
            raise TypeError(f"Expected bool control type, got {self.ctrl._type}")

    def create(self, parent):
        assert dpg is not None
        valdefault = self.ctrl.value_default
        if not isinstance(valdefault, bool):
            raise TypeError(f"Expected bool for TickBoxControl default, got {type(valdefault)}")

        # DPG callback signature: (sender, app_data, user_data)
        user_data = (self.name, self.update_func)

        tag = f"{self.name}_checkbox"
        self.control_widget = dpg.add_checkbox(
            label=self.ctrl.name,
            default_value=valdefault,
            callback=lambda s, a, u: u[1](u[0], a),
            user_data=user_data,
            parent=parent,
            tag=tag,
        )

        if self.ctrl.tooltip:
            with dpg.tooltip(self.control_widget):
                dpg.add_text(self.ctrl.tooltip)

        return self.control_widget

    def reset(self):
        assert dpg is not None
        value = self.ctrl.value
        if not isinstance(value, bool):
            raise TypeError(f"Expected bool for TickBoxControl value, got {type(value)}")
        dpg.set_value(self.control_widget, value)


class DropdownMenuControl(BaseControl):
    """Dropdown/combo box control using dpg.add_combo()."""

    def check_control_type(self):
        if self.ctrl._type is not str:
            raise TypeError(f"Expected str control type, got {self.ctrl._type}")
        if not hasattr(self.ctrl, "value_range"):
            raise ValueError("Invalid control type")

    def create(self, parent):
        assert dpg is not None
        if self.ctrl.value_range is None:
            raise ValueError("value_range must be set for DropdownMenuControl")

        # Convert all items to strings
        items = [str(item) if not isinstance(item, str) else item for item in self.ctrl.value_range]

        # Find default value index
        value = self.ctrl.value
        value_str = str(value) if not isinstance(value, str) else value
        default_value = value_str if value_str in items else items[0]

        # DPG callback: receives index, need to convert to value
        def combo_callback(sender, app_data, user_data):
            idx = items.index(app_data) if app_data in items else 0
            name, update_func = user_data
            update_func(name, idx)

        user_data = (self.name, self.update_func)

        tag = f"{self.name}_combo"
        self.control_widget = dpg.add_combo(
            items=items,
            default_value=default_value,
            callback=combo_callback,
            user_data=user_data,
            parent=parent,
            tag=tag,
            width=-1,
        )

        if self.ctrl.tooltip:
            with dpg.tooltip(self.control_widget):
                dpg.add_text(self.ctrl.tooltip)

        return self.control_widget

    def reset(self):
        assert dpg is not None
        value = self.ctrl.value
        value_str = str(value) if not isinstance(value, str) else value
        dpg.set_value(self.control_widget, value_str)


class PromptControl(BaseControl):
    """Text input control using dpg.add_input_text()."""

    def check_control_type(self):
        if self.ctrl._type is not str:
            raise TypeError(f"Expected str control type, got {self.ctrl._type}")
        if self.ctrl.value_range is not None:
            raise ValueError("value_range must be None for PromptControl")

    def create(self, parent):
        assert dpg is not None
        value = self.ctrl.value
        value_str = str(value) if not isinstance(value, str) else value

        # DPG callback signature: (sender, app_data, user_data)
        user_data = (self.name, self.update_func)

        tag = f"{self.name}_input"
        self.control_widget = dpg.add_input_text(
            default_value=value_str,
            callback=lambda s, a, u: u[1](u[0], a),
            user_data=user_data,
            parent=parent,
            tag=tag,
            width=-1,
        )

        if self.ctrl.tooltip:
            with dpg.tooltip(self.control_widget):
                dpg.add_text(self.ctrl.tooltip)

        return self.control_widget

    def reset(self):
        assert dpg is not None
        value = self.ctrl.value
        value_str = str(value) if not isinstance(value, str) else value
        dpg.set_value(self.control_widget, value_str)


class IconButtonsControl(BaseControl):
    """Icon button control using dpg.add_image_button()."""

    def check_control_type(self):
        if self.ctrl._type is not str:
            raise TypeError(f"Expected str control type, got {self.ctrl._type}")
        if not hasattr(self.ctrl, "value_range") or not hasattr(self.ctrl, "icons"):
            raise ValueError("Invalid control type or missing value range for icons bar creation.")

    def create(self, parent):
        assert dpg is not None
        if self.ctrl.value_range is None:
            raise ValueError("value_range must be set for IconButtonsControl")
        if self.ctrl.icons is None:
            raise ValueError("icons must be set for IconButtonsControl")

        # Create a horizontal group for icon buttons
        group_tag = f"{self.name}_icon_group"
        dpg.add_group(horizontal=True, parent=parent, tag=group_tag)

        self.control_widgets = []
        self.texture_tags = []

        # Load and create textures for each icon
        for idx, icon_path in enumerate(self.ctrl.icons):
            # Load image and create texture
            icon_path_obj = Path(icon_path)
            if not icon_path_obj.exists():
                logging.warning(f"Icon file not found: {icon_path}")
                continue

            try:
                # Load image using DPG's load_image
                width, height, channels, data = dpg.load_image(str(icon_path_obj))

                # Create static texture
                texture_tag = f"{self.name}_icon_{idx}"
                with dpg.texture_registry():
                    dpg.add_static_texture(width=width, height=height, default_value=data, tag=texture_tag)

                self.texture_tags.append(texture_tag)

                # Create image button
                def button_callback(sender, app_data, user_data):
                    button_idx, name, update_func = user_data
                    update_func(name, button_idx)

                button_user_data = (idx, self.name, self.update_func)
                button_tag = f"{self.name}_button_{idx}"
                dpg.add_image_button(
                    texture_tag=texture_tag,
                    callback=button_callback,
                    user_data=button_user_data,
                    parent=group_tag,
                    tag=button_tag,
                    width=64,
                    height=64,
                )

                if self.ctrl.tooltip:
                    with dpg.tooltip(button_tag):
                        dpg.add_text(f"{self.ctrl.tooltip} - {self.ctrl.value_range[idx]}")

                self.control_widgets.append(button_tag)

            except Exception as e:
                logging.warning(f"Failed to load icon {icon_path}: {e}")
                continue

        return group_tag

    def reset(self):
        # Icon buttons don't have a visual "selected" state in this implementation
        pass
