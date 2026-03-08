# Panel

::: interactive_pipe.headless.panel.Panel

The `Panel` class organizes controls into logical groups with optional collapsible sections, nested hierarchies, and detached windows. Panels help create cleaner, more organized user interfaces.

## Basic Usage

```python
from interactive_pipe import interactive, Control, Panel

# Create a panel
lighting_panel = Panel("Lighting Settings")

# Assign controls to the panel using the group parameter
@interactive(
    brightness=Control(0.5, [0.0, 1.0], name="Brightness", group=lighting_panel),
    contrast=Control(1.0, [0.5, 2.0], name="Contrast", group=lighting_panel)
)
def adjust_lighting(img, brightness=0.5, contrast=1.0):
    result = img * brightness
    result = (result - 0.5) * contrast + 0.5
    return result
```

## Parameters

- `name` (str | None) - Display name for the panel (shown in group box title)
- `collapsible` (bool) - Whether the panel can be collapsed/expanded (default: False)
- `collapsed` (bool) - Initial collapsed state if collapsible=True (default: False)
- `detached` (bool) - Whether to render panel in a separate window (Qt backend only, default: False)
- `detached_size` (tuple | None) - Optional (width, height) tuple for detached window size
- `position` (str | None) - Position relative to images: "left", "right", "top", "bottom", or None (default: "bottom")

## Panel Features

### Collapsible Panels

Create panels that can be collapsed to save screen space:

```python
from interactive_pipe import Panel, Control, interactive

# Collapsible panel, initially expanded
basic_panel = Panel("Basic Settings", collapsible=True, collapsed=False)

# Collapsible panel, initially collapsed
advanced_panel = Panel("Advanced Settings", collapsible=True, collapsed=True)

@interactive(
    brightness=Control(0.5, [0.0, 1.0], group=basic_panel),
    gamma=Control(1.0, [0.5, 2.0], group=advanced_panel)
)
def adjust_image(img, brightness=0.5, gamma=1.0):
    result = img * brightness
    result = np.power(result, 1.0/gamma)
    return result
```

### Detached Panels

Create panels that open in separate windows (Qt backend only):

```python
from interactive_pipe import Panel, Control, interactive

# Detached panel with custom window size
tools_panel = Panel(
    "Tools",
    detached=True,
    detached_size=(400, 600)  # width, height in pixels
)

@interactive(
    tool_param=Control(0.5, [0.0, 1.0], group=tools_panel)
)
def apply_tool(img, tool_param=0.5):
    return img * tool_param
```

### Panel Positioning

Control where panels appear relative to the image display:

```python
from interactive_pipe import Panel, Control, interactive

# Left sidebar
left_panel = Panel("Tools", position="left")

# Right sidebar
right_panel = Panel("Settings", position="right")

# Top bar
top_panel = Panel("Filters", position="top")

# Bottom bar (default)
bottom_panel = Panel("Controls", position="bottom")

@interactive(
    tool1=Control(0.5, [0.0, 1.0], group=left_panel),
    setting1=Control(1.0, [0.5, 2.0], group=right_panel),
    filter1=Control("normal", ["normal", "high"], group=top_panel),
    adjust1=Control(True, group=bottom_panel)
)
def process_image(img, tool1=0.5, setting1=1.0, filter1="normal", adjust1=True):
    return img
```

Valid positions:

- `"left"` - Panel appears on the left side
- `"right"` - Panel appears on the right side
- `"top"` - Panel appears at the top
- `"bottom"` - Panel appears at the bottom (default if None)
- `None` - Default positioning (bottom)

### Nested Panels with Grid Layout

Create hierarchical panel structures with grid layouts:

```python
from interactive_pipe import Panel, Control, interactive

# Create child panels
text_panel = Panel("Text", collapsible=True)
color_panel = Panel("Colors", collapsible=True)
effects_panel = Panel("Effects", collapsible=True)

# Create parent panel with nested layout
main_panel = Panel("Image Editing").add_elements([
    [text_panel, color_panel],  # Row 1: side by side
    [effects_panel],            # Row 2: full width
])

# Assign controls to child panels
@interactive(
    font_size=Control(12, [8, 48], group=text_panel),
    saturation=Control(1.0, [0.0, 2.0], group=color_panel),
    blur=Control(0.0, [0.0, 10.0], group=effects_panel)
)
def edit_image(img, font_size=12, saturation=1.0, blur=0.0):
    # ... processing ...
    return img
```

The `add_elements()` method accepts:

- **List of Panels**: `[panel1, panel2, panel3]` - Vertical stack
- **List of lists**: `[[panel1, panel2], [panel3]]` - Grid layout (row-major)

### String-based Panel Groups

For simple use cases, you can use strings instead of Panel objects. Interactive Pipe automatically creates and caches panels:

```python
from interactive_pipe import interactive, Control

@interactive(
    brightness=Control(0.5, [0.0, 1.0], group="Lighting"),
    contrast=Control(1.0, [0.5, 2.0], group="Lighting"),
    saturation=Control(1.0, [0.0, 2.0], group="Color")
)
def adjust_image(img, brightness=0.5, contrast=1.0, saturation=1.0):
    return img
```

This automatically creates two panels named "Lighting" and "Color". All controls with the same string will be grouped together.

!!! note "String vs Panel Objects"
    Using explicit `Panel` objects gives you more control (collapsible, detached, positioning), while strings are convenient for simple grouping.

## Complete Example

Here's a comprehensive example showing various panel features:

```python
from interactive_pipe import (
    interactive,
    interactive_pipeline,
    Control,
    Panel
)
import numpy as np

# Create panel hierarchy
# Main panel for lighting
lighting_panel = Panel("Lighting", collapsible=True, collapsed=False)

# Child panels within lighting
contrast_panel = Panel("Contrast", collapsible=True, collapsed=False)
stretching_panel = Panel("Stretching", collapsible=True, collapsed=True)

# Nested structure
lighting_panel.add_elements([[contrast_panel, stretching_panel]])

# Separate color panel
color_panel = Panel("Color", collapsible=True, collapsed=False)

# Detached tools panel
tools_panel = Panel(
    "Tools",
    detached=True,
    detached_size=(300, 400)
)

@interactive(
    # Contrast controls
    black_point=Control(0.0, [0.0, 1.0], name="Black Point", group=contrast_panel),
    white_point=Control(1.0, [0.0, 1.0], name="White Point", group=contrast_panel),
    
    # Stretching controls
    gamma=Control(1.0, [0.0, 2.0], name="Gamma", group=stretching_panel),
    contrast=Control(1.0, [0.0, 2.0], name="Contrast", group=stretching_panel),
    
    # Color controls
    saturation=Control(1.0, [0.0, 2.0], name="Saturation", group=color_panel),
    hue=Control(0.0, [0.0, 360.0], name="Hue Shift", group=color_panel),
    
    # Tool controls in detached window
    sharpen=Control(0.0, [0.0, 1.0], name="Sharpen", group=tools_panel),
    denoise=Control(0.0, [0.0, 1.0], name="Denoise", group=tools_panel)
)
def process_image(
    img,
    black_point=0.0,
    white_point=1.0,
    gamma=1.0,
    contrast=1.0,
    saturation=1.0,
    hue=0.0,
    sharpen=0.0,
    denoise=0.0
):
    """Process image with organized controls."""
    result = img.copy()
    
    # Apply contrast stretching
    result = (result - black_point) / (white_point - black_point + 1e-10)
    result = np.clip(result, 0.0, 1.0)
    
    # Apply gamma
    result = np.power(result, 1.0 / gamma)
    
    # Apply contrast
    result = (result - 0.5) * contrast + 0.5
    
    # Apply color adjustments
    gray = result.mean(axis=2, keepdims=True)
    result = gray + (result - gray) * saturation
    
    # Apply tools
    # ... sharpen, denoise ...
    
    return np.clip(result, 0.0, 1.0)

@interactive_pipeline(gui='qt', name="Image Editor")
def image_editor(img):
    processed = process_image(img)
    return [img, processed]

# Launch
if __name__ == "__main__":
    test_img = np.random.rand(512, 512, 3)
    image_editor(test_img)
```

## Panel Properties

After creation, you can access panel properties:

```python
panel = Panel("Settings", collapsible=True, collapsed=True)

# Access properties
print(panel.name)          # "Settings"
print(panel.collapsible)   # True
print(panel.collapsed)     # True
print(panel.detached)      # False
print(panel.position)      # None (default: "bottom")

# Internal properties
print(panel.elements)      # List of child panels or grid
print(panel.parent)        # Parent panel (None if root)
print(panel._controls)     # List of controls assigned to this panel

# Get root panel in hierarchy
root = panel.get_root()
```

## Best Practices

### Organization Strategy

1. **Logical Grouping**: Group related controls together (e.g., all lighting controls in one panel)
2. **Hierarchy**: Use nested panels for complex interfaces with many controls
3. **Initial State**: Collapse advanced panels by default, keep basic controls expanded
4. **Detached Windows**: Use for specialized tools that benefit from separate windows

### Example Organization

```python
# Good: Logical grouping
basic_panel = Panel("Basic Adjustments")      # Common controls
advanced_panel = Panel("Advanced", collapsible=True, collapsed=True)
tools_panel = Panel("Tools", detached=True)   # Specialized tools

# Less ideal: Everything in one panel
all_controls = Panel("All Controls")  # Can become cluttered
```

### Naming

Use clear, descriptive panel names:

```python
# Good
Panel("Image Adjustments")
Panel("Color Correction")
Panel("Filters & Effects")

# Less clear
Panel("Panel1")
Panel("Stuff")
Panel("Options")
```

## Backend Support

| Feature | Qt | Matplotlib | Notebook | Gradio |
|---------|----|-----------:|----------|--------|
| Basic grouping | ✅ | ✅ | ✅ | ✅ |
| Collapsible | ✅ | ❌ | ✅ | ✅ |
| Detached windows | ✅ | ❌ | ❌ | ❌ |
| Positioning | ✅ | ⚠️ | ⚠️ | ⚠️ |
| Nested panels | ✅ | ⚠️ | ⚠️ | ⚠️ |

✅ Fully supported  
⚠️ Partially supported or limited  
❌ Not supported

## See Also

- [Controls](controls.md) - Complete reference for control types
- [Decorators](decorators.md) - Using panels with `@interactive`
- [User Guide: Controls](../guide/controls.md) - Tutorials and examples
tut