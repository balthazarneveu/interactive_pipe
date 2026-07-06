# Context, layout & events

Filters communicate with each other and with the display through proxies importable from `interactive_pipe`: `context`, `layout` and `events` (a fourth proxy, `audio`, has [its own page](audio.md)).

!!! note "`global_params` was removed in 0.9.0"
    The pre-0.9.0 pattern of declaring `global_params={}` (or `context`, `state`, ...) in a filter signature now raises `TypeError` at filter construction. The proxies below replace it entirely — see the [changelog](../changelog.md) for the migration guide.

## `context` — share data between filters

```python
from interactive_pipe import interactive, context

@interactive(color_choice=["red", "green", "blue", "gray"])
def generate_flat_colored_image(color_choice="red"):
    flat_array = COLOR_DICT[color_choice] * np.ones((64, 64, 3))
    context["avg"] = np.average(flat_array)   # dict-style
    context.avg = np.average(flat_array)      # or attribute-style
    return flat_array

def special_image_slice(img):
    out_img = img.copy()
    if context["avg"] > 0.4:                  # read what another filter stored
        out_img[out_img.shape[0] // 2:, ...] = 0.
    return out_img
```

`get_context()` returns the underlying shared dictionary directly. You can seed it at pipeline construction: `@interactive_pipeline(gui="qt", context={"avg": 0.0})`.

## `layout` — arrange and style the outputs

Output names are the **variable names used in the pipeline function**:

```python
from interactive_pipe import layout

def change_layout(layout_mode: str = "side_by_side"):
    if layout_mode == "side_by_side":
        layout.grid([["input", "result"]])
    if layout_mode == "grid2x2":
        layout.grid([["input", "processed"], ["histogram_graph", "result"]])
    layout.style("result", title="Final Result")

def pipeline(input):
    processed = denoise(input)
    result = change_brightness(processed)
    histogram_graph = compute_histo(processed)
    change_layout()
    return result
```

Live layout switching (e.g. going from a side-by-side comparison to a 2x2 grid) is supported on the Qt backend.

## `events` — key-bound one-shot flags

Read-only flags raised by GUI key bindings for a single pipeline run — see [Keyboard](keyboard.md#key-bound-one-shot-events).

## API

Full reference: [Context & layout](../api/context.md).
