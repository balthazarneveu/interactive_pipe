# Decorators

Decorators are the main entry points for creating interactive pipelines with Interactive Pipe. They allow you to add interactive controls to your functions without writing any GUI code.

## @interactive

::: interactive_pipe.helper.filter_decorator.interactive

The `@interactive` decorator adds interactive controls to a filter function. It does **not** launch a GUI immediately - it simply declares that the function should have controls.

### Usage

```python
from interactive_pipe import interactive

@interactive(
    brightness=(0.5, [0.0, 1.0]),
    contrast=(1.0, [0.5, 2.0])
)
def adjust_image(img, brightness=0.5, contrast=1.0):
    """Apply brightness and contrast adjustments."""
    adjusted = img * brightness
    adjusted = (adjusted - 0.5) * contrast + 0.5
    return adjusted
```

### Control Declaration

Controls are declared as keyword arguments to the decorator. See [Control Abbreviation Syntax](controls.md#abbreviation-syntax) for shorthand notation, or use explicit `Control` objects:

```python
from interactive_pipe import interactive, Control

@interactive(
    threshold=Control(0.5, [0.0, 1.0], name="Threshold", tooltip="Binary threshold value")
)
def threshold_filter(img, threshold=0.5):
    return img > threshold
```

### Using in Pipelines

Decorated functions can be used in pipeline functions:

```python
from interactive_pipe import interactive_pipeline

@interactive_pipeline(gui='qt')
def my_pipeline(img):
    brightened = adjust_image(img)  # Uses controls from @interactive
    thresholded = threshold_filter(brightened)
    return [img, brightened, thresholded]
```

## @interactive_pipeline

::: interactive_pipe.helper.pipeline_decorator.interactive_pipeline

The `@interactive_pipeline` decorator creates an interactive pipeline with a GUI. This is the primary decorator for building complete interactive applications.

### Usage

```python
from interactive_pipe import interactive_pipeline, interactive

@interactive(brightness=(0.5, [0.0, 1.0]))
def adjust_brightness(img, brightness=0.5):
    return img * brightness

@interactive(threshold=(0.5, [0.0, 1.0]))
def threshold_image(img, threshold=0.5):
    return img > threshold

@interactive_pipeline(gui='qt', cache=False)
def processing_pipeline(img):
    # Pipeline function must contain ONLY function calls
    # No if/else/for/while statements allowed!
    brightened = adjust_brightness(img)
    binary = threshold_image(brightened)
    return [img, brightened, binary]

# Launch the GUI
import numpy as np
img = np.random.rand(256, 256, 3)
processing_pipeline(img)
```

### Parameters

- `gui='auto'` - Backend to use ('qt', 'mpl', 'nb', 'gradio', or 'auto')
  - `'qt'` - PyQt/PySide desktop application (recommended)
  - `'mpl'` - Matplotlib backend
  - `'nb'` - Jupyter notebook with ipywidgets
  - `'gradio'` - Gradio web interface (supports `share_gradio_app=True`)
  - `None` - Returns headless pipeline (no GUI)
- `safe_input_buffer_deepcopy=True` - Deep copy inputs for safety
- `cache=False` - Enable caching of intermediate results for faster updates
- `output_canvas=None` - Custom output grid layout (2D list of output names)
- `markdown_description=None` - Markdown description for Gradio backend
- `name=None` - Pipeline name (defaults to function name)
- `**kwargs_gui` - Additional backend-specific parameters

### Important Pipeline Constraints

!!! warning "Pipeline Function Restrictions"
    Pipeline functions must contain **ONLY function calls**. No control flow statements (`if`, `else`, `for`, `while`) are allowed because the AST parser analyzes the function to build the execution graph.
    
    ```python
    # ✅ CORRECT - only function calls
    def my_pipeline(img):
        processed = process_image(img)
        filtered = apply_filter(processed)
        return [processed, filtered]
    
    # ❌ WRONG - contains if statement
    def my_pipeline(img):
        processed = process_image(img)
        if some_condition:  # This will break!
            return [processed]
        return [processed, filtered]
    ```
    
    If you need conditional logic, handle it inside individual filter functions instead.

### Context API (Modern Approach)

Use the new context API instead of the deprecated `global_params`:

```python
from interactive_pipe import interactive_pipeline, interactive, context, layout

@interactive(brightness=(0.5, [0.0, 1.0]))
def adjust_brightness(img, brightness=0.5):
    result = img * brightness
    # Set display title dynamically
    layout.style("result", title=f"Brightness: {brightness:.2f}")
    # Share data with other filters
    context["brightness_value"] = brightness
    return result

@interactive_pipeline(gui='qt')
def my_pipeline(img):
    result = adjust_brightness(img)
    return [img, result]
```

## See Also

- [Controls](controls.md) - Complete reference for control types
- [Context API](context.md) - Modern API for shared state
- [User Guide](../guide/filters.md) - Tutorials and examples
