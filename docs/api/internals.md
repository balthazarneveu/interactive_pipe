# Internal API

This page documents internal APIs primarily intended for advanced users, debugging, or library development. For typical usage, refer to the main [API Reference](index.md).

## @interact (One-Shot Decorator)

::: interactive_pipe.helper.filter_decorator.interact

The `@interact` decorator is a **one-shot** decorator that immediately launches a GUI when the function is decorated. This is primarily useful for quick experimentation and testing single filters during development.

!!! warning "Not Recommended for Production"
    For production code and reusable pipelines, use `@interactive` combined with `@interactive_pipeline` instead. The `@interact` decorator is mainly intended for quick prototyping in notebooks or scripts.

### Usage

```python
from interactive_pipe import interact
import numpy as np

# Create test data
img = np.random.rand(100, 100, 3)

@interact(
    img,  # Input data
    brightness=(0.5, [0.0, 1.0]),
    gui='qt'
)
def adjust_brightness(img, brightness=0.5):
    return img * brightness
```

### Key Differences from @interactive

- `@interact` **launches a GUI immediately** when the function is decorated
- First positional arguments are treated as input data
- After the decorated function runs, it returns the **original function** (not a GUI object)
- Cannot be composed into pipelines easily

### Parameters

- `*decorator_args` - Input data to pass to the filter
- `gui='auto'` - Backend to use ('qt', 'mpl', 'nb', 'gradio', or 'auto')
- `disable=False` - If True, disables GUI and returns original function
- `output_routing=None` - List of output names (auto-detected if None)
- `size=None` - Window size tuple (width, height)
- `**decorator_controls` - Control definitions (same as @interactive)

### When to Use

- Quick experimentation in Jupyter notebooks
- Rapid prototyping of a single filter
- Testing a filter in isolation

### Recommended Alternative

For reusable, composable code:

```python
from interactive_pipe import interactive, interactive_pipeline

@interactive(brightness=(0.5, [0.0, 1.0]))
def adjust_brightness(img, brightness=0.5):
    return img * brightness

@interactive_pipeline(gui='qt')
def my_pipeline(img):
    result = adjust_brightness(img)
    return [img, result]

# Launch
my_pipeline(img)
```

## get_context()

::: interactive_pipe.core.context.get_context

The `get_context()` function returns the shared context dictionary. This is a lower-level alternative to the `context` proxy object.

!!! note "Prefer Using `context` Proxy"
    For most use cases, use the `context` proxy directly (e.g., `context["key"] = value`). The `get_context()` function is provided for compatibility and edge cases where you need the actual dictionary.

### Usage

```python
from interactive_pipe import interactive, get_context

@interactive()
def my_filter(img):
    ctx = get_context()
    
    # Now use ctx as a regular dict
    ctx["my_data"] = compute_data(img)
    other_data = ctx.get("other_key", default_value)
    
    return img
```

### Equivalence

These are equivalent:

```python
# Using context proxy (recommended)
from interactive_pipe import context
context["key"] = value

# Using get_context()
from interactive_pipe import get_context
ctx = get_context()
ctx["key"] = value
```

### When to Use

- When you need to pass the context dictionary to another function
- When you need the actual dict object (not a proxy)
- For compatibility with existing code patterns

## @pipeline (Headless Pipeline)

::: interactive_pipe.helper.pipeline_decorator.pipeline

The `@pipeline` decorator creates a **headless pipeline** without a GUI. It's equivalent to `@interactive_pipeline(gui=None)`.

### Usage

```python
from interactive_pipe import pipeline, interactive

@interactive(threshold=(0.5, [0.0, 1.0]))
def threshold_filter(img, threshold=0.5):
    return img > threshold

@pipeline
def batch_processing(img):
    return threshold_filter(img)

# Use for batch processing
import numpy as np
imgs = [np.random.rand(100, 100, 3) for _ in range(10)]
results = [batch_processing(img) for img in imgs]
```

### When to Use

- Batch processing of multiple files
- Testing pipelines without GUI overhead
- Server-side processing
- CI/CD pipelines and automated testing

## block (Alias for @interactive)

`block` is simply an alias for `@interactive`, provided for alternative naming preferences:

```python
from interactive_pipe import block

# These are equivalent:
@block(param=(0.5, [0.0, 1.0]))
def my_filter(img, param=0.5):
    return img * param

# Same as:
@interactive(param=(0.5, [0.0, 1.0]))
def my_filter(img, param=0.5):
    return img * param
```

## FilterError

::: interactive_pipe.core.engine.FilterError

`FilterError` is raised when a filter function fails during execution. It wraps the original exception with additional context about which filter failed.

### When You Might Encounter This

- During development when a filter raises an exception
- When debugging pipeline execution issues

For typical usage, you don't need to explicitly catch `FilterError` - the pipeline will report the error with full context automatically.

## See Also

- [API Reference Overview](index.md) - Main API documentation
- [Context API](context.md) - Modern context proxy API
- [Decorators](decorators.md) - Main decorator documentation
