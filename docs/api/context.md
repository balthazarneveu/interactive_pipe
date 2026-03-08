# Context API

The Context API provides a clean way to share data between filters and control display properties without polluting function signatures. This replaces the deprecated `global_params={}` pattern.

## Overview

The Context API consists of three main components:

- **`context`** - Shared state dictionary for passing data between filters
- **`layout`** - Display control (titles, styles, grid arrangement)
- **`audio`** - Audio playback control (Gradio backend)

All three use Python's `contextvars` behind the scenes, ensuring thread-safety and proper isolation.

## context

::: interactive_pipe.core.context._ContextProxy

The `context` proxy provides dict-like access to shared state between filters. Use it to pass computed values, detected objects, or any data from one filter to another.

### Basic Usage

```python
from interactive_pipe import interactive, context

@interactive()
def detect_objects(img):
    """Detect objects and store results in context."""
    objects = find_objects(img)
    
    # Store in context for next filter
    context["detected_objects"] = objects
    context["object_count"] = len(objects)
    
    return img_with_boxes

@interactive()
def analyze_objects(img):
    """Use detected objects from previous filter."""
    # Retrieve from context
    objects = context.get("detected_objects", [])
    count = context.get("object_count", 0)
    
    # Use the data
    analysis = analyze(objects)
    return analysis_visualization
```

### Dict-like Operations

The `context` proxy supports standard dictionary operations:

```python
# Set values
context["key"] = value
context.update({"key1": value1, "key2": value2})

# Get values
value = context["key"]              # Raises KeyError if not found
value = context.get("key", default)  # Returns default if not found

# Check existence
if "key" in context:
    print("Key exists")

# Delete
del context["key"]
context.pop("key", default)

# Iterate
for key, value in context.items():
    print(f"{key}: {value}")

# Clear all
context.clear()
```

### Attribute-style Access

For convenience, you can also use attribute-style access:

```python
# Set attributes
context.my_data = "value"

# Get attributes
value = context.my_data

# Note: This raises AttributeError if key doesn't exist
# For safe access, use .get() instead:
value = context.get("my_data", default)
```

## layout

::: interactive_pipe.core.context._LayoutProxy

The `layout` proxy controls display properties and output arrangements. It replaces the old `global_params["__output_styles"]` pattern.

### style() - Set Display Properties

Set titles, colormaps, and other display properties for outputs:

```python
from interactive_pipe import interactive, layout

@interactive(threshold=(0.5, [0.0, 1.0]))
def threshold_image(img, threshold=0.5):
    result = img > threshold
    
    # Set dynamic title
    layout.style("result", title=f"Threshold: {threshold:.2f}")
    
    return result
```

#### Full style() Signature

```python
layout.style(
    name: str,           # Output variable name
    title: str = None,   # Display title
    **style_kwargs       # Additional style properties
)
```

Additional style properties (backend-dependent):

- `colormap` - Matplotlib colormap name (e.g., "viridis", "gray")
- `vmin`, `vmax` - Value range for colormap
- `interpolation` - Image interpolation method
- Any other backend-specific properties

#### Examples

```python
# Simple title
layout.style("output", title="Processed Image")

# With colormap
layout.style("heatmap", title="Heat Map", colormap="hot", vmin=0, vmax=1)

# Multiple outputs
layout.style("original", title="Input")
layout.style("filtered", title="After Filter")
layout.style("result", title="Final Result")
```

#### Alias: set_style()

`set_style()` is an alias for `style()`:

```python
layout.set_style("output", title="My Title")  # Same as layout.style()
```

### grid() - Set Output Layout

Control the arrangement of outputs in a grid:

```python
from interactive_pipe import interactive, layout

@interactive()
def process_multiple(img):
    output1 = process1(img)
    output2 = process2(img)
    output3 = process3(img)
    output4 = process4(img)
    
    # Arrange in 2x2 grid
    layout.grid([
        ["output1", "output2"],
        ["output3", "output4"]
    ])
    
    return output1, output2, output3, output4
```

#### Grid Patterns

```python
# Single row
layout.grid([["img1", "img2", "img3"]])

# Single column
layout.grid([["img1"], ["img2"], ["img3"]])

# 2x2 grid
layout.grid([
    ["img1", "img2"],
    ["img3", "img4"]
])

# Mixed layout
layout.grid([
    ["header"],              # Full width
    ["left", "right"],       # Two columns
    ["footer"]               # Full width
])
```

#### Aliases

Multiple aliases are available:

```python
layout.set_grid([...])   # Alias for grid()
layout.canvas([...])     # Alias for grid()
layout.set_canvas([...]) # Alias for grid()
```

### row() - Convenience for Single Row

For single-row layouts, use the `row()` convenience method:

```python
from interactive_pipe import interactive, layout

@interactive()
def process_image(img):
    original = img
    filtered = apply_filter(img)
    result = finalize(filtered)
    
    # Arrange in single row
    layout.row(["original", "filtered", "result"])
    
    return original, filtered, result
```

This is equivalent to:

```python
layout.grid([["original", "filtered", "result"]])
```

## audio

::: interactive_pipe.core.context._AudioProxy

The `audio` proxy controls audio playback (Gradio backend only). Use it to play audio files or control playback from within filters.

### set() - Set Audio File

```python
from interactive_pipe import interactive, audio

@interactive(track=(0, [0, 5]))
def audio_player(img, track=0):
    tracks = ["song1.mp3", "song2.mp3", "song3.mp3"]
    
    # Set audio file to play
    audio.set(tracks[track])
    
    return img
```

### play() - Start Playback

```python
@interactive()
def start_music(img):
    audio.set("background.mp3")
    audio.play()
    return img
```

### pause() - Pause Playback

```python
@interactive(paused=False)
def control_playback(img, paused=False):
    if paused:
        audio.pause()
    else:
        audio.play()
    return img
```

### stop() - Stop Playback

```python
@interactive()
def stop_music(img):
    audio.stop()
    return img
```

!!! note "Backend Support"
    Audio control is currently only supported in the Gradio backend. Other backends will silently ignore audio commands.

## Complete Example

Here's a comprehensive example using all Context API features:

```python
from interactive_pipe import (
    interactive,
    interactive_pipeline,
    context,
    layout,
    audio
)
import numpy as np

@interactive(threshold=(0.5, [0.0, 1.0]))
def detect_features(img, threshold=0.5):
    """Detect features and store in context."""
    # Detect features
    features = img > threshold
    feature_count = int(features.sum())
    
    # Store in context for next filter
    context["features"] = features
    context["feature_count"] = feature_count
    
    # Set display title
    layout.style("features", title=f"Features: {feature_count}")
    
    return features

@interactive(min_size=(10, [5, 100]))
def filter_features(img, min_size=10):
    """Use features from previous filter."""
    # Get data from context
    features = context.get("features", np.zeros_like(img))
    count = context.get("feature_count", 0)
    
    # Filter by size
    filtered = filter_by_size(features, min_size)
    remaining = int(filtered.sum())
    
    # Update context
    context["filtered_features"] = filtered
    context["remaining_count"] = remaining
    
    # Set display
    layout.style("filtered", title=f"Filtered: {remaining}/{count}")
    
    return filtered

@interactive()
def visualize_results(img):
    """Create final visualization."""
    features = context.get("features", np.zeros_like(img))
    filtered = context.get("filtered_features", np.zeros_like(img))
    count = context.get("remaining_count", 0)
    
    # Create visualizations
    overlay = create_overlay(img, filtered)
    stats = create_stats_image(count)
    
    # Set grid layout
    layout.grid([
        ["img", "overlay"],
        ["stats", "filtered"]
    ])
    
    # Set titles
    layout.style("img", title="Original")
    layout.style("overlay", title="Feature Overlay")
    layout.style("stats", title="Statistics")
    layout.style("filtered", title="Final Features")
    
    # Play success sound (Gradio only)
    if count > 10:
        audio.set("success.mp3")
        audio.play()
    
    return img, overlay, stats, filtered

@interactive_pipeline(gui='qt', name="Feature Detection")
def feature_pipeline(img):
    features = detect_features(img)
    filtered = filter_features(img)
    result = visualize_results(img)
    return result

# Launch
if __name__ == "__main__":
    test_img = np.random.rand(256, 256, 3)
    feature_pipeline(test_img)
```

## Migration from global_params

If you have old code using `global_params`, here's how to migrate:

### Old Pattern (Deprecated)

```python
# ❌ OLD - Deprecated
@interactive(brightness=(0.5, [0.0, 1.0]))
def old_filter(img, brightness=0.5, global_params={}):
    result = img * brightness
    
    # Old way to set title
    global_params["__output_styles"]["result"] = {
        "title": f"Brightness: {brightness}"
    }
    
    # Old way to share data
    global_params["my_data"] = compute_data(img)
    
    return result
```

### New Pattern (Recommended)

```python
# ✅ NEW - Clean API
from interactive_pipe import interactive, context, layout

@interactive(brightness=(0.5, [0.0, 1.0]))
def new_filter(img, brightness=0.5):
    result = img * brightness
    
    # New way to set title
    layout.style("result", title=f"Brightness: {brightness}")
    
    # New way to share data
    context["my_data"] = compute_data(img)
    
    return result
```

### Benefits of New API

1. **Cleaner signatures** - No `global_params={}` parameter
2. **Explicit purpose** - `context` for data, `layout` for display, `audio` for sound
3. **Better IDE support** - Type hints and autocomplete work properly
4. **Thread-safe** - Uses Python's `contextvars` for proper isolation
5. **More Pythonic** - Dict-like interface feels natural

## Error Handling

If you call Context API functions outside of filter execution, you'll get clear errors:

```python
from interactive_pipe import context, layout

# ❌ Called outside filter - raises RuntimeError
context["key"] = "value"
# RuntimeError: get_context() called outside of pipeline execution.

layout.style("output", title="Title")
# RuntimeError: Framework operation called outside of filter execution.
```

These functions must be called from within a filter decorated with `@interactive` and executed through an interactive pipeline.

## See Also

- [Decorators](decorators.md) - Using Context API with `@interactive`
- [User Guide: Filters](../guide/filters.md) - Tutorials and examples
- [Controls](controls.md) - Interactive parameter controls
