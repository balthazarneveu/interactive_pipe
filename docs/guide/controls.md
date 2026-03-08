# Controls & Widgets

## Overview

Controls in Interactive Pipe define how parameters can vary and how they are displayed in the GUI. They automatically create appropriate widgets based on the parameter type.

## Control Types

### Float/Int Sliders

Create sliders for numeric parameters:

```python
from interactive_pipe import interactive, Control

@interactive(
    coeff=Control(1.0, [0.5, 2.0], name="exposure coefficient"),
    bias=Control(0, [-0.2, 0.2], name="offset")
)
def exposure(img, coeff=1.0, bias=0):
    return img * coeff + bias
```

**Abbreviated syntax:**

```python
@interactive()
def exposure(img, coeff=(1.0, [0.5, 2.0], "exposure"), bias=(0, [-0.2, 0.2])):
    return img * coeff + bias
```

### Boolean Checkboxes

Create checkboxes for boolean parameters:

```python
@interactive(
    bnw=Control(True, name="Black and White")
)
def black_and_white(img, bnw=True):
    if bnw:
        return np.repeat(np.expand_dims(np.average(img, axis=-1), -1), img.shape[-1], axis=-1)
    return img
```

**Abbreviated syntax:**

```python
@interactive()
def black_and_white(img, bnw=(True, "black and white")):
    # ...
```

### Dropdown Menus

Create dropdown menus for string lists:

```python
COLOR_DICT = {
    "red": [1., 0., 0.],
    "green": [0., 1., 0.],
    "blue": [0., 0., 1.],
    "gray": [0.5, 0.5, 0.5]
}

@interactive()
def generate_flat_colored_image(color_choice=["red", "green", "blue", "gray"]):
    '''Generate a constant colorful image'''
    flat_array = np.array(COLOR_DICT.get(color_choice)) * np.ones((64, 64, 3))
    return flat_array
```

The first element of the list will be the default value.

**Note:** In v0.8.8, dropdown menus are automatically hidden when only a single choice is available.

## Keyboard Controls

You can create controls that respond to keyboard shortcuts instead of displaying widgets:

```python
from interactive_pipe import interactive

@interactive()
def switch_image(img1, img2, img3, image_index=(0, [0, 2], None, ["pagedown", "pageup", True])):
    '''Switch between 3 images using PageDown/PageUp keys'''
    return [img1, img2, img3][image_index]
```

Format: `(default, [min, max], label, [key_down, key_up, wrap_around])`

- `key_down`: Key to decrease the value
- `key_up`: Key to increase the value
- `wrap_around`: If `True`, the value wraps around (goes back to min after max)

For boolean controls:

```python
@interactive()
def toggle_effect(img, enabled=(True, "special effect", "k")):
    '''Press 'k' to toggle the effect'''
    if enabled:
        return apply_effect(img)
    return img
```

## Keyboard Shortcuts

While using the GUI (Qt & Matplotlib backends):

- `F1` - Show help shortcuts in the terminal
- `F11` - Toggle fullscreen mode
- `W` - Write full resolution image to disk
- `R` - Reset parameters
- `I` - Print parameters dictionary in the command line
- `E` - Export parameters dictionary to a yaml file
- `O` - Import parameters dictionary from a yaml file (sliders will update)
- `G` - Export a pipeline diagram (requires graphviz)

## Special Controls

### Text Prompt

```python
@interactive()
def add_text(img, message=("Hello World!", None)):
    '''Display custom text'''
    # message is a free text input
    return add_text_to_image(img, message)
```

### Time Control

```python
from interactive_pipe import interactive

@interactive()
def animate(img, time=(0.0, [0, 10], "time")):
    '''Animate over time'''
    return apply_time_based_effect(img, time)
```

TimeControl allows you to play/pause time using an incrementing timer.

### Circular Sliders

Available in Qt backend for parameters that represent angles or cyclic values:

```python
@interactive()
def rotate(img, angle=(0., [-360., 360.], "rotation")):
    '''Rotate image'''
    return apply_rotation(img, angle)
```

## Control Behavior Notes

- If you write `def blend(img0, img1, blend_coeff=0.5)` (no tuple), `blend_coeff` will NOT be a slider
- If you write `blend_coeff=[0., 1.]`, `blend_coeff` will be a slider initialized to 0.5
- If you write `bnw=(True, "black and white", "k")`, the checkbox becomes a keyboard control (press `k` to toggle)

## Filters Without Inputs

You can create filters that generate images without inputs:

```python
@interactive()
def generate_checkerboard(size=(8, [4, 32], "grid size")):
    '''Generate a checkerboard pattern'''
    # Creates a checkerboard without requiring an input image
    return create_checkerboard(size)
```
