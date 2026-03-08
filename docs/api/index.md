# API Reference Overview

This page provides a complete reference for the public API of Interactive Pipe. All classes, functions, and objects listed here are imported directly from the `interactive_pipe` package.

## Import Convention

```python
import interactive_pipe as ip

# Or import specific components
from interactive_pipe import interactive, Control, Image, context, layout
```

## Quick Reference

### Decorators

The main entry points for creating interactive pipelines:

- **[@interactive](decorators.md#interactive)** - Decorate filter functions to add interactive controls
- **[@interactive_pipeline](decorators.md#interactive_pipeline)** - Create an interactive pipeline with GUI

### Controls

Interactive parameter controls that create GUI widgets:

- **[Control](controls.md#control)** - Base control class for sliders, dropdowns, and checkboxes
- **[CircularControl](controls.md#circularcontrol)** - Circular/dial slider (Qt backend only)
- **[TextPrompt](controls.md#textprompt)** - Free text input field
- **[TimeControl](controls.md#timecontrol)** - Timer with play/pause functionality
- **[KeyboardControl](controls.md#keyboardcontrol)** - Keyboard-triggered parameter changes (no visible slider)

**See also:** [Control Abbreviation Syntax](controls.md#abbreviation-syntax) for shorthand notation

### Organization

- **[Panel](panel.md)** - Organize controls into groups with collapsible sections and detached windows

### Data Objects

Specialized data containers for images, curves, and tables:

- **[Image](data_objects.md#image)** - Image data wrapper with load/save capabilities
- **[Curve](data_objects.md#curve)** - Multiple curves for 2D plotting
- **[SingleCurve](data_objects.md#singlecurve)** - Single x,y curve data
- **[Table](data_objects.md#table)** - Tabular data display

### Context API

Clean API for shared state and display control (replaces deprecated `global_params`):

- **[context](context.md#context)** - Proxy for shared state between filters (dict-like access)
- **[layout](context.md#layout)** - Display control (titles, styles, grid arrangement)
- **[audio](context.md#audio)** - Audio playback control (Gradio backend)

### Constants

- **`__version__`** - Package version string

## Common Usage Patterns

### Basic Filter with Slider

```python
from interactive_pipe import interactive

@interactive(brightness=(0.5, [0.0, 1.0]))
def adjust_brightness(img, brightness=0.5):
    return img * brightness
```

### Pipeline with Multiple Filters

```python
from interactive_pipe import interactive_pipeline

@interactive_pipeline(gui='qt')
def my_pipeline(img):
    enhanced = enhance_image(img)
    filtered = apply_filter(enhanced)
    return [img, enhanced, filtered]
```

### Sharing Data Between Filters

```python
from interactive_pipe import interactive, context

@interactive()
def detect_objects(img):
    objects = find_objects(img)
    context["detected_objects"] = objects  # Share with next filter
    return annotated_img

@interactive()
def analyze_objects(img):
    objects = context.get("detected_objects", [])
    return analysis_result
```

### Custom Display Titles

```python
from interactive_pipe import interactive, layout

@interactive(threshold=(0.5, [0.0, 1.0]))
def threshold_image(img, threshold=0.5):
    result = img > threshold
    layout.style("result", title=f"Threshold: {threshold:.2f}")
    return result
```

## Next Steps

- [Decorators Documentation](decorators.md) - Detailed guide to `@interactive` and pipelines
- [Controls Documentation](controls.md) - Complete reference for all control types
- [Context API Documentation](context.md) - Modern API for shared state and display control
- [User Guide](../guide/filters.md) - Tutorials and examples
