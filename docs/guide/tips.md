# Tips & tricks

## Generator filters (no inputs)

Filters don't have to take image inputs — they can simply *generate* data:

```python
from interactive_pipe import interactive, context
import numpy as np

COLOR_DICT = {"red": [1., 0., 0.], "green": [0., 1., 0.], "blue": [0., 0., 1.], "gray": [0.5, 0.5, 0.5]}

@interactive(color_choice=["red", "green", "blue", "gray"])
def generate_flat_colored_image(color_choice="red"):
    flat_array = np.array(COLOR_DICT.get(color_choice)) * np.ones((64, 64, 3))
    context["avg"] = np.average(flat_array)
    return flat_array
```

The `color_choice` list becomes a dropdown menu; the default is the first element.

## Switching between images

```python
@interactive(image_index=(0, [0, 2], None, ["pagedown", "pageup", True]))
def switch_image(img1, img2, img3, image_index=0):
    return [img1, img2, img3][image_index]
```

The `["pagedown", "pageup", True]` part binds the index to keys; `True` makes it wrap around (back to 0 past the maximum).

## Avoid in-place operations

There are no checks that inputs aren't modified in place (that would cost copies and hashing everywhere). By default the pipeline deep-copies the *input* buffers (`safe_input_buffer_deepcopy=True`), but intermediate buffers are your responsibility:

```python
# Don't do this!
def bad_processing_block(inp):
    inp += 1
```

## Cache intermediate results

`@interactive_pipeline(gui="qt", cache=True)` keeps intermediate filter outputs in RAM, so moving a slider only re-runs the filters downstream of the change — a big win for heavy pipelines.

## Export / import tuning

Press ++e++ in the GUI to export the current parameters to YAML and ++o++ to load them back; headless pipelines expose the same via `export_tuning()` / `load_tuning()`. Press ++g++ to export a graphviz diagram of the pipeline.

## One-shot GUI with `@interact`

For a quick experiment on a *single* function — no pipeline needed — `@interact` opens the GUI immediately at decoration time:

```python
from interactive_pipe import interact
import numpy as np

image = np.random.rand(256, 512, 3)

@interact(image, gain=(1.0, [0.0, 3.0]))
def show(img, gain=1.0):
    return img * gain
```

Handy in notebooks and throwaway scripts; for anything reusable, prefer `@interactive` + `@interactive_pipeline` ([decorators guide](decorators.md)).

::: interactive_pipe.interact
