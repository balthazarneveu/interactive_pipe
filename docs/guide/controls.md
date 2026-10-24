# Controls

A control binds a GUI widget to a filter keyword argument. Declare controls in the `@interactive()` decorator; the widget type is inferred from the default value's type and the presence of a range.

## Two equivalent styles

The same control can always be written as a **tuple shorthand** — great for prototyping — or as an **explicit object** — clearer in larger codebases and required for the extra arguments (`step`, `icons`, `tooltip`, ...):

=== "Tuple shorthand"

    ```python
    from interactive_pipe import interactive

    @interactive(gain=(1.0, [0.5, 2.0], "exposure"))
    def exposure(img, gain=1.0):
        return img * gain
    ```

    The tuple order is `(default, range, name, group)` — trailing elements are optional.

=== "Explicit object"

    ```python
    from interactive_pipe import interactive, Control

    @interactive(gain=Control(1.0, [0.5, 2.0], name="exposure"))
    def exposure(img, gain=1.0):
        return img * gain
    ```

    `Control` unlocks every option: `Control(1.0, [0.5, 2.0], name="exposure", step=0.05, group="Panel A", tooltip="scene brightness")`.

!!! tip "Even shorter"
    A bare range works too: `@interactive(blend_coeff=[0., 1.])` creates a slider initialized to the middle of the range, and `@interactive(mode=["dark", "light"])` a dropdown defaulting to the first choice.

Specialized widgets (keyboard, circular slider, range slider, timer) only exist as explicit objects.

## Declaration patterns

| You want | Tuple shorthand | Explicit object |
|---|---|---|
| Float slider | `gain=(1.0, [0.5, 2.0])` | `gain=Control(1.0, [0.5, 2.0])` |
| ... with a custom label | `gain=(1.0, [0.5, 2.0], "exposure")` | `gain=Control(1.0, [0.5, 2.0], name="exposure")` |
| Int slider (step 1) | `size=(5, [1, 15])` | `size=Control(5, [1, 15])` |
| Checkbox | `flip=(True,)` | `flip=Control(True)` |
| Dropdown | `mode=("light", ["dark", "light"])` | `mode=Control("light", ["dark", "light"])` |
| Dropdown, first choice as default | `mode=["dark", "light"]` | — |
| Free text box | `txt=("Hello world!", None)` | `txt=TextPrompt("Hello world!")` |
| Grouped in a panel | `gain=(1.0, [0.5, 2.0], "gain", "Panel A")` | `gain=Control(1.0, [0.5, 2.0], group="Panel A")` |
| Key-driven value ([Keyboard](keyboard.md)) | — | `idx=KeyboardControl(0, [0, 2], keydown="pagedown", keyup="pageup", modulo=True)` |
| Circular slider (Qt, Dear PyGui) | — | `angle=CircularControl(90, [0, 360], modulo=True)` |
| Min/max range ([below](#range-control)) | — | `window=RangeControl((0.2, 0.8), [0.0, 1.0])` |
| Animated timer | — | `t=TimeControl(update_interval_ms=50)` |

See the [Control API reference](../api/controls.md) for every argument.

## Range control

`RangeControl` picks an interval with two handles: the filter receives a `(lo, hi)` tuple, always sorted (`lo <= hi`) and within `value_range`.

```python
import numpy as np
from interactive_pipe import interactive, RangeControl

@interactive(levels=RangeControl((0.2, 0.8), [0.0, 1.0], name="input levels"))
def stretch_levels(img, levels=(0.2, 0.8)):
    lo, hi = levels
    return np.clip((img - lo) / (hi - lo), 0.0, 1.0)
```

- Elements are ints when the default and the range are all ints (`RangeControl((2, 5), [0, 10])`), floats otherwise; `step` defaults to 1 or 1/100 of the range, like `Control`.
- An invalid default (`lo > hi`, outside the range, not a pair) raises `ValueError`/`TypeError`; later updates are sorted and clamped instead.
- Tuning files store the value as a 2-element list (`"levels": [0.2, 0.8]`); importing it gives the filter a tuple again.
- When the decorator declares the control, the signature default (`levels=(0.2, 0.8)`) is just the plain value — it is not read as tuple shorthand.

| Backend | Widget |
|---|---|
| Qt | two linked sliders (lo above, hi below) — dragging one past the other pushes it |
| Dear PyGui | two linked sliders, same rule |
| Matplotlib | native `matplotlib.widgets.RangeSlider` |
| Notebook | `ipywidgets` `IntRangeSlider` / `FloatRangeSlider` |
| Gradio | text box holding `lo, hi` (no built-in range slider) |

## Image buttons (Qt, Dear PyGui)

A string dropdown can be rendered as image buttons by providing one icon per choice:

```python
@interactive(song=Control("song_a", ["song_a", "song_b"], icons=["a.png", "b.png"]))
def choose_song(song="song_a"):
    ...
```

This is how the [jukebox demo](https://github.com/balthazarneveu/interactive_pipe/blob/master/demo/jukebox_demo.py) works.

## Grouping controls

Pass `group="Panel name"` (or a [`Panel`](panels.md) instance) to gather related controls together in the GUI.

## Decorating without `@`

Applying the decorator "from outside" keeps your library free of interactive_pipe imports:

```python
from core_filters import processing_block
from interactive_pipe import interactive

interactive(angle=(0., [-360., 360.]))(processing_block)
```

## Exporting an animation

A pipeline driven by a `TimeControl` can be rendered to an animated GIF or to a PNG frame sequence.
Frame `k` is computed with the time control set to `k / fps` seconds.

**From the GUI**: press `v` (or **Pipeline → Export animation** in the menu bar) and pick a `.gif` or `.png` path.
The GUI renders 5 seconds at 10 fps; the result (or the error) is printed in the message area.

**Headless**, with full control over the settings:

```python
from interactive_pipe import export_animation
from interactive_pipe.headless.pipeline import HeadlessPipeline

pipe = HeadlessPipeline.from_function(pipeline, cache=False)
pipe.inputs = []  # the pipeline function inputs, if any
export_animation(pipe, "waves.gif", duration=4.0, fps=20)          # animated GIF, loops forever
export_animation(pipe, "frames/", duration=2.0, fps=25, output=1)  # frames/frames_0000.png, ...
```

- `path`: a `.gif` file writes an animated GIF (Pillow); a directory, a `.png` path or a path without suffix
  writes numbered PNG frames `<stem>_0000.png`, `<stem>_0001.png`, ...
- `duration` (seconds) and `fps` set the number of frames (`int(duration * fps)`).
- `output`: which output to record — an index into the outputs, a `(row, col)` cell of a 2D layout,
  or `None` (default) for the first non-empty output. Outputs must be images (float arrays in `[0, 1]`,
  grayscale or RGB); curves, tables and text raise a `TypeError`.
- `time_control`: the control name, needed only when the pipeline has several `TimeControl`s.
- `loop`: GIF loop count (`0` = forever).

The time control value is restored when the export is done, so the GUI state is unchanged.
