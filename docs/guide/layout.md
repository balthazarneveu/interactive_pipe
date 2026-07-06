# Layout

## The simplest way: return the grid

The pipeline function's return statement *is* the layout. Return a flat tuple for a single row, or a nested list to arrange the outputs in a grid — no extra code:

```python
@interactive_pipeline(gui="qt")
def pipe(img):
    a = exposure(img)
    b = black_and_white(img)
    c = blend(a, b)
    d = compute_histo(c)
    return [[a, b], [c, d]]   # 2x2 grid
```

- `return a, b, c` — one row of three.
- `return [[a, b], [c, d]]` — 2×2 grid.
- `return [[a], [b]]` — one column of two (stacked).
- `return [[a, b], [c, None]]` — `None` leaves a cell empty.

## Dynamic layouts: the `layout` proxy

For layouts that *change at runtime* — driven by a slider, a dropdown, or the data itself — use the `layout` proxy from inside any filter. Output names are the **variable names used in the pipeline function**:

```python
from interactive_pipe import layout

@interactive(layout_mode=["side_by_side", "grid2x2"])
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

Live layout switching (e.g. going from a side-by-side comparison to a 2x2 grid while the app runs) is supported on the Qt backend.

## `layout` methods

::: interactive_pipe.core.context._LayoutProxy
    options:
      show_root_heading: false
      show_source: false
