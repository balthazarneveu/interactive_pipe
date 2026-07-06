# Layout

The `layout` proxy, importable from `interactive_pipe`, arranges and styles the displayed outputs from inside any filter. Output names are the **variable names used in the pipeline function**:

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

- `layout.grid(...)` takes a flat list (single row) or a 2D list of output names.
- `layout.row([...])` is a convenience for a single row.
- `layout.style(name, title=..., **style_kwargs)` sets display properties for one output.

Live layout switching (e.g. going from a side-by-side comparison to a 2x2 grid) is supported on the Qt backend.

## API

Full reference: [the `layout` proxy](../api/context.md).
