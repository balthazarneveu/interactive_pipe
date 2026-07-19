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
from interactive_pipe import KeyboardControl

@interactive(image_index=KeyboardControl(0, [0, 2], keydown="pagedown", keyup="pageup", modulo=True))
def switch_image(img1, img2, img3, image_index=0):
    return [img1, img2, img3][image_index]
```

`modulo=True` makes the index wrap around (back to 0 past the maximum) — flip through images with ++page-up++ / ++page-down++.

## Avoid in-place operations

Filters route their buffers by reference, so mutating an input in place silently corrupts sibling filters and cached buffers. Since 0.9.1, inputs are handed to filters as **read-only views by default** (`readonly_inputs=True`), so the mistake raises immediately instead of producing wrong results:

```python
# Raises since 0.9.1 — img is a read-only view
def bad_processing_block(img):
    img += 1
    return img
```

If a filter *intentionally* mutates its inputs, declare it with `@interactive(inplace=True)` — it then receives private writable copies:

```python
@interactive(inplace=True)
def add_one(img):
    img += 1
    return img
```

Pass `readonly_inputs=False` to `@interactive_pipeline(...)` to restore the old permissive behavior. In-place mutation is also detected for torch tensors (which cannot be marked read-only).

## Cache intermediate results

`@interactive_pipeline(gui="qt", cache=True)` keeps intermediate filter outputs in RAM, so moving a slider only re-runs the filters downstream of the change (in source order) — a big win for heavy pipelines.

For pipelines with **independent branches**, use `cache="graph"` instead: this dependency-aware mode recomputes a filter only when it is actually affected — its own sliders moved, one of its producers was recomputed, or a `context` key it reads changed. Filters on branches unrelated to the change are left untouched.

```python
@interactive_pipeline(gui="qt", cache="graph")
def my_pipeline(img):
    exposed = exposure(img)   # moving the exposure slider...
    smooth = denoise(img)     # ...leaves denoise and annotate cached
    tagged = annotate(smooth)
    return [exposed, tagged]
```

Use `cache="graph-strict"` to additionally receive `context` numpy arrays as read-only views, catching accidental in-place mutation of shared context data.

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
