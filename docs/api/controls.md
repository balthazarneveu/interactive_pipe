# Controls

Controls are interactive widgets that allow users to adjust parameters in real-time. They automatically generate sliders, dropdowns, checkboxes, and other UI elements based on parameter types and ranges.

## Control

::: interactive_pipe.headless.control.Control

The base `Control` class creates different widget types based on the parameter type:

- **Numeric sliders** (int/float with range)
- **Dropdowns** (string with list of choices)
- **Checkboxes** (boolean)
- **Free-range inputs** (numeric without range)

### Basic Usage

```python
from interactive_pipe import interactive, Control

@interactive(
    brightness=Control(0.5, [0.0, 1.0], name="Brightness"),
    mode=Control("normal", ["normal", "high", "low"], name="Mode"),
    enabled=Control(True, name="Enable Filter")
)
def my_filter(img, brightness=0.5, mode="normal", enabled=True):
    if not enabled:
        return img
    result = img * brightness
    return result
```

### Parameters

- `value_default` (int | float | bool | str) - Default value and determines control type
- `value_range` (list | None) - For numeric: `[min, max]`; for string: list of choices
- `name` (str | None) - Display name (auto-generated if None)
- `step` (int | float | None) - Step size (auto-calculated if None)
- `filter_to_connect` (FilterCore | None) - Internal use
- `parameter_name_to_connect` (str | None) - Internal use
- `icons` (list | None) - List of icon paths for button-style controls
- `group` (str | Panel | None) - Panel to organize this control in
- `tooltip` (str | None) - Tooltip text shown on hover

### Control Types by Value Type

#### Numeric Slider (int/float with range)

```python
# Integer slider: 0 to 100, default 50
Control(50, [0, 100])

# Float slider: 0.0 to 1.0, default 0.5
Control(0.5, [0.0, 1.0])

# Custom step size
Control(0.5, [0.0, 1.0], step=0.01)
```

#### Dropdown (string with choices)

```python
# String dropdown
Control("medium", ["small", "medium", "large"])
```

#### Checkbox (boolean)

```python
# Checkbox (no range allowed)
Control(True)
Control(False, name="Enable Feature")
```

#### Free-range Input (numeric without range)

```python
# Free-range integer input
Control(42)

# Free-range float input
Control(3.14)
```

### Grouping with Panels

```python
from interactive_pipe import interactive, Control, Panel

# Create panels
lighting_panel = Panel("Lighting", collapsible=True)
color_panel = Panel("Colors", collapsible=True, collapsed=True)

@interactive(
    brightness=Control(0.5, [0.0, 1.0], group=lighting_panel),
    contrast=Control(1.0, [0.5, 2.0], group=lighting_panel),
    saturation=Control(1.0, [0.0, 2.0], group=color_panel),
    hue=Control(0.0, [0.0, 360.0], group=color_panel)
)
def adjust_image(img, brightness=0.5, contrast=1.0, saturation=1.0, hue=0.0):
    # ... processing ...
    return img
```

### Icons for Button Controls

```python
from pathlib import Path

# Create button-style controls with icons
Control(
    "cat",
    ["cat", "dog", "bird"],
    icons=[
        Path("icons/cat.png"),
        Path("icons/dog.png"),
        Path("icons/bird.png")
    ]
)
```

## CircularControl

::: interactive_pipe.headless.control.CircularControl

A circular/dial slider widget (Qt backend only). Useful for angles, hue, or other cyclic parameters.

### Usage

```python
from interactive_pipe import interactive, CircularControl

@interactive(
    angle=CircularControl(0.0, [0.0, 360.0], modulo=True, name="Rotation Angle")
)
def rotate_image(img, angle=0.0):
    # Rotate image by angle degrees
    return rotated_img
```

### Parameters

All parameters from `Control`, plus:

- `modulo` (bool) - If True, wrapping around is enabled (e.g., 360° → 0°)

### Example with Modulo

```python
# With modulo=True: turning past 360° wraps to 0°
CircularControl(0.0, [0.0, 360.0], modulo=True)

# With modulo=False: stops at 360°
CircularControl(0.0, [0.0, 360.0], modulo=False)
```

## TextPrompt

::: interactive_pipe.headless.control.TextPrompt

A free text input field for string parameters without predefined choices.

### Usage

```python
from interactive_pipe import interactive, TextPrompt

@interactive(
    caption=TextPrompt("Hello World", name="Image Caption")
)
def add_text(img, caption="Hello World"):
    # Add caption text to image
    return annotated_img
```

### Parameters

- `value_default` (str) - Default text value
- `name` (str | None) - Display name
- `filter_to_connect` (FilterCore | None) - Internal use
- `parameter_name_to_connect` (str | None) - Internal use
- `group` (str | Panel | None) - Panel to organize this control in
- `tooltip` (str | None) - Tooltip text

### Example with Tooltip

```python
TextPrompt(
    "Enter text here",
    name="Custom Text",
    tooltip="Enter the text to overlay on the image"
)
```

## TimeControl

::: interactive_pipe.headless.control.TimeControl

A timer control that automatically increments with play/pause functionality. Useful for animations and time-based effects.

### Usage

```python
from interactive_pipe import interactive, TimeControl

@interactive(
    time=TimeControl(
        name="Time",
        update_interval_ms=50,  # Update 20 times per second
        pause_resume_key="p"
    )
)
def animate_effect(img, time=0.0):
    # Create time-based animation
    phase = time * 2 * 3.14159  # Convert to radians
    effect = np.sin(phase)
    return img * (0.5 + 0.5 * effect)
```

### Parameters

- `name` (str | None) - Display name
- `update_interval_ms` (int) - Update interval in milliseconds (default: 1000)
- `pause_resume_key` (str) - Keyboard key to pause/resume (default: "p")
- `filter_to_connect` (FilterCore | None) - Internal use
- `parameter_name_to_connect` (str | None) - Internal use
- `group` (str | Panel | None) - Panel to organize this control in
- `tooltip` (str | None) - Tooltip text

### Interaction

- Press the configured key (default: "p") to pause/resume the timer
- Time starts at 0.0 and increments based on the update interval
- Range is [0.0, 3600.0] seconds (1 hour)

## KeyboardControl

::: interactive_pipe.headless.keyboard.KeyboardControl

A control that responds to keyboard input without displaying a slider widget. Useful for parameters you want to adjust with keyboard shortcuts.

### Usage

```python
from interactive_pipe import interactive, KeyboardControl

@interactive(
    zoom=KeyboardControl(
        1.0,
        [0.5, 3.0],
        keydown="+",
        keyup="-",
        step=0.1,
        name="Zoom Level"
    )
)
def zoom_image(img, zoom=1.0):
    # Scale image by zoom factor
    return scaled_img
```

### Parameters

All parameters from `Control`, plus:

- `keydown` (str | None) - Key to decrease value (or toggle for bool)
- `keyup` (str | None) - Key to increase value
- `modulo` (bool) - If True, wrap around at range boundaries

### Special Keys

Single character keys: `'a'`, `'b'`, `'1'`, `'2'`, etc.

Special keys:

- `'up'`, `'down'`, `'left'`, `'right'` - Arrow keys
- `'pageup'`, `'pagedown'` - Page navigation
- `' '` - Spacebar
- `'f1'` through `'f12'` - Function keys

### Examples

#### Numeric Parameter with Keyboard

```python
# Use arrow keys to adjust value
KeyboardControl(
    0.5,
    [0.0, 1.0],
    keydown="down",
    keyup="up",
    step=0.05
)
```

#### Boolean Toggle

```python
# Press spacebar to toggle
KeyboardControl(
    False,
    keydown=" ",
    name="Show Overlay"
)
```

#### String Dropdown with Keyboard

```python
# Cycle through modes with left/right arrows
KeyboardControl(
    "normal",
    ["normal", "high", "low"],
    keydown="left",
    keyup="right",
    modulo=True  # Wrap around at boundaries
)
```

#### Modulo Wrapping

```python
# Angle control that wraps: 360° → 0°, -1° → 359°
KeyboardControl(
    0.0,
    [0.0, 360.0],
    keydown="left",
    keyup="right",
    modulo=True,
    step=15.0
)
```

## Abbreviation Syntax

For convenience, Interactive Pipe supports shorthand tuple/list notation for declaring controls. This is more concise than creating explicit `Control` objects.

### Basic Patterns

```python
from interactive_pipe import interactive

@interactive(
    # Numeric slider: (default, [min, max])
    brightness=(0.5, [0.0, 1.0]),
    
    # Numeric slider with step: (default, [min, max, step])
    contrast=(1.0, [0.5, 2.0, 0.1]),
    
    # String dropdown: (default, [choice1, choice2, ...])
    mode=("normal", ["normal", "high", "low"]),
    
    # Checkbox: (bool,) or just bool
    enabled=(True,),
    invert=False,  # Can also use bare bool
)
def my_filter(img, brightness=0.5, contrast=1.0, mode="normal", enabled=True, invert=False):
    return img
```

### Ultra-Short Patterns

When you don't need to specify a default value, you can use even shorter syntax:

```python
@interactive(
    # Range-first: ([min, max],) - default is midpoint
    brightness=([0.0, 1.0],),  # Default: 0.5
    
    # Range-first with step: ([min, max, step],)
    contrast=([0.5, 2.0, 0.1],),  # Default: 1.25
    
    # Range-first with custom default: ([min, max, step, default],)
    saturation=([0.0, 2.0, None, 1.0],),  # Default: 1.0, auto step
    
    # Choices-first: (["choice1", "choice2"],) - first is default
    mode=(["normal", "high", "low"],),  # Default: "normal"
)
def my_filter(img, brightness=0.5, contrast=1.25, saturation=1.0, mode="normal"):
    return img
```

### Adding Names and Groups

You can add names and panel groups to abbreviated controls:

```python
from interactive_pipe import interactive, Panel

panel = Panel("Settings")

@interactive(
    # (default, range, name)
    brightness=(0.5, [0.0, 1.0], "Brightness"),
    
    # (default, range, name, group)
    contrast=(1.0, [0.5, 2.0], "Contrast", panel),
    
    # (bool, name, group)
    enabled=(True, "Enable Filter", panel),
)
def my_filter(img, brightness=0.5, contrast=1.0, enabled=True):
    return img
```

### When to Use Explicit Controls

Use explicit `Control` objects when you need:

- Tooltips
- Icons
- Fine control over step size
- More descriptive code

```python
# Abbreviated (concise)
@interactive(brightness=(0.5, [0.0, 1.0]))

# Explicit (more features)
@interactive(
    brightness=Control(
        0.5,
        [0.0, 1.0],
        name="Brightness",
        tooltip="Adjust image brightness (0=black, 1=normal)",
        step=0.01
    )
)
```

### KeyboardControl Note

!!! note "Keyboard Controls Not Supported in Abbreviations"
    `KeyboardControl` cannot be created using abbreviation syntax. You must use explicit instantiation:
    
    ```python
    from interactive_pipe import interactive, KeyboardControl
    
    @interactive(
        zoom=KeyboardControl(1.0, [0.5, 3.0], keydown="-", keyup="+")
    )
    ```

## Complete Example

Here's a comprehensive example using various control types:

```python
from interactive_pipe import (
    interactive,
    interactive_pipeline,
    Control,
    CircularControl,
    TextPrompt,
    TimeControl,
    KeyboardControl,
    Panel
)
import numpy as np

# Create panels for organization
lighting_panel = Panel("Lighting", collapsible=True)
effects_panel = Panel("Effects", collapsible=True, collapsed=True)
text_panel = Panel("Text Overlay")

@interactive(
    # Abbreviated numeric sliders
    brightness=(0.5, [0.0, 1.0], "Brightness", lighting_panel),
    contrast=(1.0, [0.5, 2.0], "Contrast", lighting_panel),
    
    # Explicit control with tooltip
    gamma=Control(1.0, [0.5, 2.0], name="Gamma", tooltip="Gamma correction", group=lighting_panel),
    
    # Circular control for angle
    rotation=CircularControl(0.0, [0.0, 360.0], modulo=True, name="Rotation", group=effects_panel),
    
    # Time-based animation
    time=TimeControl(name="Animation Time", update_interval_ms=50, group=effects_panel),
    
    # Keyboard-controlled zoom
    zoom=KeyboardControl(1.0, [0.5, 3.0], keydown="-", keyup="+", name="Zoom"),
    
    # Text input
    caption=TextPrompt("Hello World", name="Caption", group=text_panel),
    
    # Checkboxes
    show_caption=(True, "Show Caption", text_panel),
)
def process_image(
    img,
    brightness=0.5,
    contrast=1.0,
    gamma=1.0,
    rotation=0.0,
    time=0.0,
    zoom=1.0,
    caption="Hello World",
    show_caption=True
):
    """Process image with various adjustments."""
    # Apply lighting adjustments
    result = img * brightness
    result = (result - 0.5) * contrast + 0.5
    result = np.power(np.clip(result, 0, 1), 1.0 / gamma)
    
    # Apply effects
    # ... rotation, zoom, animation ...
    
    # Add caption if enabled
    if show_caption:
        # ... add text overlay ...
        pass
    
    return result

@interactive_pipeline(gui='qt')
def demo_pipeline(img):
    processed = process_image(img)
    return [img, processed]

# Launch with test image
if __name__ == "__main__":
    test_img = np.random.rand(256, 256, 3)
    demo_pipeline(test_img)
```

## See Also

- [Panel Documentation](panel.md) - Organize controls into groups
- [Decorators](decorators.md) - Using controls with `@interactive` and `@interact`
- [User Guide: Controls](../guide/controls.md) - Tutorials and examples
