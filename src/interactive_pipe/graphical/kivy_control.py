from interactive_pipe.headless.control import Control
import logging
import os

# Disable Kivy's argument parser to avoid conflicts with argparse
# This must be set BEFORE importing any Kivy modules
os.environ.setdefault("KIVY_NO_ARGS", "1")

KIVY_AVAILABLE = False
try:
    from kivy.uix.slider import Slider
    from kivy.uix.checkbox import CheckBox
    from kivy.uix.spinner import Spinner
    from kivy.uix.textinput import TextInput
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.widget import Widget
    from kivy.uix.image import Image as KivyImage
    from kivy.uix.behaviors import ButtonBehavior
    from kivy.clock import Clock
    from kivy.graphics import Rectangle, Line, Color

    KIVY_AVAILABLE = True
except ImportError:
    logging.warning("Kivy not available")


class BorderedCheckBox(CheckBox):
    """CheckBox with a subtle border around the checkbox square for better visibility."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Use a subtle border color that matches Qt's style
        self.border_color = (0.6, 0.6, 0.6, 1)  # Light gray, subtle
        self.border_width = 1
        self.bind(pos=self._update_border, size=self._update_border)
        Clock.schedule_once(lambda dt: self._update_border(), 0.01)

    def _update_border(self, *args):
        """Update the border around the checkbox square."""
        if not hasattr(self, "_border_added"):
            # Use canvas.after to draw border on top of the checkbox square
            with self.canvas.after:
                Color(*self.border_color)
                self._checkbox_border = Line(width=self.border_width)
            self._border_added = True

        if hasattr(self, "_checkbox_border"):
            # Kivy's CheckBox draws the square centered, sized based on height
            # For a 40px widget, the square is typically ~18-20px (about 45-50% of height)
            # Use a size that matches Kivy's default checkbox square rendering
            checkbox_size = min(
                self.height * 0.48, self.width * 0.48
            )  # ~48% matches Kivy's ~18-20px for 40px widget
            # Center the square in the widget (Kivy centers it)
            checkbox_x = self.x + (self.width - checkbox_size) / 2
            checkbox_y = self.y + (self.height - checkbox_size) / 2

            # Draw border rectangle around the checkbox square itself (not the whole widget)
            self._checkbox_border.rectangle = (
                checkbox_x,
                checkbox_y,
                checkbox_size,
                checkbox_size,
            )


class BorderedSlider(Slider):
    """Slider with subtle borders on the track and knob for better visibility."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Subtle border colors matching Qt's style
        self.track_border_color = (0.6, 0.6, 0.6, 1)  # Light gray
        self.knob_border_color = (0.55, 0.55, 0.55, 1)  # Slightly darker
        self.border_width = 1

        self.bind(
            pos=self._update_borders,
            size=self._update_borders,
            value=self._update_borders,
        )
        Clock.schedule_once(lambda dt: self._update_borders(), 0.01)

    def _update_borders(self, *args):
        """Update borders on slider track and knob."""
        if not hasattr(self, "_borders_added"):
            # Use canvas.before for better integration
            with self.canvas.before:
                Color(*self.track_border_color)
                self._track_border = Line(width=self.border_width)
                Color(*self.knob_border_color)
                self._knob_border = Line(width=self.border_width)
            self._borders_added = True

        self._update_border_positions()

    def _update_border_positions(self):
        """Update the positions of track and knob borders."""
        if not hasattr(self, "_track_border") or not hasattr(self, "_knob_border"):
            return

        # Get padding
        padding = getattr(self, "padding", 16)
        if isinstance(padding, (list, tuple)):
            padding_x = padding[0] if len(padding) > 0 else 16
        else:
            padding_x = padding

        # Track dimensions (match Kivy's rendering)
        track_height = max(2, int(self.height * 0.08))  # ~8% of height, min 2px
        track_y = self.y + (self.height - track_height) / 2
        track_x = self.x + padding_x
        track_width = max(0, self.width - 2 * padding_x)

        self._track_border.rectangle = (track_x, track_y, track_width, track_height)

        # Knob position - calculate from value
        value_range = self.max - self.min
        if value_range > 0:
            value_normalized = (self.value - self.min) / value_range
        else:
            value_normalized = 0

        knob_x = track_x + value_normalized * track_width
        knob_y = self.y + self.height / 2
        knob_radius = max(5, int(self.height * 0.18))  # ~18% of height

        self._knob_border.circle = (knob_x, knob_y, knob_radius)


class BaseControl:
    def __init__(self, name, ctrl: Control, update_func, silent=False):
        self.name = name
        self.ctrl = ctrl
        self.update_func = update_func
        self.control_widget = None
        self.silent = silent
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
        if not KIVY_AVAILABLE:
            raise ModuleNotFoundError("Kivy is not installed")
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
        assert self.ctrl._type == int

    def create(self):
        layout = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=40, size_hint_x=1.0
        )
        label = Label(
            text=self.name, size_hint_x=0.3, size_hint_y=1.0, color=(0, 0, 0, 1)
        )
        layout.add_widget(label)

        slider = BorderedSlider(
            min=self.ctrl.value_range[0],
            max=self.ctrl.value_range[1],
            value=self.ctrl.value_default,
            step=1,
            size_hint_x=0.5,
            size_hint_y=1.0,
            sensitivity="all",
        )

        # Use Clock to throttle updates during dragging
        slider._pending_refresh = None

        def on_value_change(instance, value):
            # Update label immediately
            value_label.text = str(int(value))
            # Cancel any pending refresh
            if slider._pending_refresh:
                Clock.unschedule(slider._pending_refresh)

            # Schedule a throttled update (refresh after 50ms of no changes)
            def delayed_update(dt):
                self.update_func(self.name, int(value))
                slider._pending_refresh = None

            slider._pending_refresh = Clock.schedule_once(delayed_update, 0.05)

        slider.bind(value=on_value_change)
        self.control_widget = slider
        layout.add_widget(slider)

        value_label = Label(
            text=str(self.ctrl.value_default),
            size_hint_x=0.2,
            size_hint_y=1.0,
            color=(0, 0, 0, 1),
        )
        self.value_label = value_label
        layout.add_widget(value_label)

        # Update value label when slider changes
        def update_label(instance, value):
            value_label.text = str(int(value))

        slider.bind(value=update_label)
        return layout

    def reset(self):
        if self.control_widget:
            self.control_widget.value = self.ctrl.value


class FloatSliderControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == float

    def convert_value_to_int(self, val):
        return int(
            (val - self.ctrl.value_range[0])
            * 1000
            / (self.ctrl.value_range[1] - self.ctrl.value_range[0])
        )

    def convert_int_to_value(self, val):
        return (
            self.ctrl.value_range[0]
            + (self.ctrl.value_range[1] - self.ctrl.value_range[0]) * val / 1000
        )

    def create(self):
        layout = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=40, size_hint_x=1.0
        )
        label = Label(
            text=self.name, size_hint_x=0.3, size_hint_y=1.0, color=(0, 0, 0, 1)
        )
        layout.add_widget(label)

        slider = BorderedSlider(
            min=0,
            max=1000,
            value=self.convert_value_to_int(self.ctrl.value_default),
            size_hint_x=0.5,
            size_hint_y=1.0,
            sensitivity="all",
        )
        self.ctrl.convert_int_to_value = self.convert_int_to_value

        # Use Clock to throttle updates during dragging
        slider._pending_refresh = None

        def on_value_change(instance, value):
            converted_value = self.convert_int_to_value(value)
            # Update label immediately
            value_label.text = f"{converted_value:.3e}"
            # Cancel any pending refresh
            if slider._pending_refresh:
                Clock.unschedule(slider._pending_refresh)

            # Schedule a throttled update (refresh after 50ms of no changes)
            def delayed_update(dt):
                self.update_func(self.name, converted_value)
                slider._pending_refresh = None

            slider._pending_refresh = Clock.schedule_once(delayed_update, 0.05)

        slider.bind(value=on_value_change)
        self.control_widget = slider
        layout.add_widget(slider)

        value_label = Label(
            text=f"{self.ctrl.value_default:.3e}",
            size_hint_x=0.2,
            size_hint_y=1.0,
            color=(0, 0, 0, 1),
        )
        self.value_label = value_label
        layout.add_widget(value_label)

        return layout

    def reset(self):
        if self.control_widget:
            self.control_widget.value = self.convert_value_to_int(self.ctrl.value)


class TickBoxControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == bool

    def create(self):
        layout = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=40, size_hint_x=1.0
        )
        checkbox = BorderedCheckBox(
            active=self.ctrl.value_default, size_hint_x=None, width=40
        )

        # Create wrapper to ignore checkbox instance argument from Kivy
        def on_active_change(instance, value):
            self.update_func(self.name, value)

        checkbox.bind(active=on_active_change)
        self.control_widget = checkbox
        layout.add_widget(checkbox)

        # Label should be left-aligned and positioned next to the checkbox
        label = Label(
            text=self.name,
            size_hint_x=1.0,
            color=(0, 0, 0, 1),
            halign="left",
            valign="middle",
        )
        # Bind text_size to size for proper text alignment
        label.bind(size=label.setter("text_size"))
        layout.add_widget(label)
        return layout

    def reset(self):
        if self.control_widget:
            self.control_widget.active = self.ctrl.value


class DropdownMenuControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == str
        if not hasattr(self.ctrl, "value_range"):
            raise ValueError("Invalid control type")

    def create(self):
        layout = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=40, size_hint_x=1.0
        )
        label = Label(
            text=self.name, size_hint_x=0.3, size_hint_y=1.0, color=(0, 0, 0, 1)
        )
        layout.add_widget(label)

        spinner = Spinner(
            text=self.ctrl.value,
            values=self.ctrl.value_range,
            size_hint_x=0.7,
            size_hint_y=1.0,
        )

        # Create wrapper to ignore spinner instance argument from Kivy
        def on_text_change(instance, text):
            self.update_func(self.name, text)

        spinner.bind(text=on_text_change)
        self.control_widget = spinner
        layout.add_widget(spinner)
        return layout

    def reset(self):
        if self.control_widget:
            self.control_widget.text = self.ctrl.value


class PromptControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == str
        assert self.ctrl.value_range is None

    def create(self):
        layout = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=40, size_hint_x=1.0
        )
        label = Label(
            text=self.name, size_hint_x=0.3, size_hint_y=1.0, color=(0, 0, 0, 1)
        )
        layout.add_widget(label)

        text_input = TextInput(
            text=str(self.ctrl.value),
            multiline=False,
            size_hint_x=0.7,
            size_hint_y=1.0,
            foreground_color=(0, 0, 0, 1),
        )

        # Create wrapper to ignore text input instance argument from Kivy
        def on_text_change(instance, text):
            self.update_func(self.name, text)

        text_input.bind(text=on_text_change)
        self.control_widget = text_input
        layout.add_widget(text_input)
        return layout

    def reset(self):
        if self.control_widget:
            self.control_widget.text = self.ctrl.value


class IconButtonsControl(BaseControl):
    def check_control_type(self):
        assert self.ctrl._type == str
        if not hasattr(self.ctrl, "value_range") or not hasattr(self.ctrl, "icons"):
            raise ValueError(
                "Invalid control type or missing value range for icons bar creation."
            )

    def create(self):
        # Create a clickable image button class using ButtonBehavior
        class ImageButton(ButtonBehavior, KivyImage):
            pass

        layout = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=80, size_hint_x=1.0
        )
        label = Label(text=self.name, size_hint_x=0.2, color=(0, 0, 0, 1))
        layout.add_widget(label)

        self.control_widgets = []
        buttons_layout = BoxLayout(
            orientation="horizontal", size_hint_x=0.8, size_hint_y=1.0
        )
        for idx, icon_name in enumerate(self.ctrl.value_range):
            icon_path = str(self.ctrl.icons[idx])

            img_btn = ImageButton(
                source=icon_path,
                size_hint_x=1.0 / len(self.ctrl.value_range),
                size_hint_y=1.0,
            )

            # Create wrapper to handle button press
            def on_press(instance, button_idx=idx):
                self.update_func(self.name, button_idx)

            img_btn.bind(on_press=on_press)
            self.control_widgets.append(img_btn)
            buttons_layout.add_widget(img_btn)
        layout.add_widget(buttons_layout)
        return layout

    def reset(self):
        # Icon buttons don't need reset as they're stateless
        pass
