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
    return [[a, b], [c, d]]  # 2x2 grid
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

Live layout switching (e.g. going from a side-by-side comparison to a 2x2 grid while the app runs) is supported on the Qt and Dear PyGui backends.

## Output style

`layout.style(name, ...)` sets how one output is displayed:

| Key | Effect |
|---|---|
| `title` | Title shown above the cell (defaults to the output name). |
| `subtitle` | Secondary text, shown after the title (`title · subtitle`). |
| `colormap` | matplotlib colormap name (`"viridis"`, `"magma"`, ...) used to display a 2D `(H, W)` array as a heatmap. |
| `vmin`, `vmax` | Values mapped to the bottom / top of the colormap (or to black / white without one) for 2D arrays. Each defaults to the data min / max, as in matplotlib. |
| `center` | Makes the range symmetric around this value (diverging colormaps: `colormap="RdBu", center=0`). |
| `colorbar` | `True` draws the scale (min, max, round ticks) to the right of a 2D array, inside the image: same on every backend and in snapshots. A string is also written along the bar as its label. |
| `unit` | Short unit written once above the colorbar (`unit="dB"`). |
| `dpi` | Pixels per inch of a matplotlib figure output (see [figure text size](figures-and-overlays.md#matplotlib-figures)). |
| `extent` | `(x_left, x_right, y_bottom, y_top)` of a 2D array (as in `imshow`): the heatmap gets axes with round ticks, drawn into the image like the colorbar ([heatmap axes](figures-and-overlays.md#heatmap-axes-extent-xlabel-ylabel)). |
| `xlabel`, `ylabel` | Axis labels: drawn with the axes of a heatmap (pixel indices without `extent`); for other images, matplotlib backend only. For curves use `Curve(..., xlabel=...)`. |

```python
@interactive()
def depth_map(img):
    layout.style("depth", title="Depth", colormap="magma", vmin=0.0, vmax=10.0)
    return estimate_depth(img)  # (H, W) float array
```

Calls on one output during a run **add up**: a later call changes only the
keys it gives, so styling once and setting a readout title later keeps the
colormap; `key=None` removes a key. The first call of the next run starts
from nothing again. Any displayed name can be styled from any filter, a
pipeline input included (`layout.style("truth", colormap="viridis")`).

### Metric readouts

A number computed by a filter (PSNR, precision / recall, a count) reads best
next to the output it describes, set every frame from the filter itself:

```python
@interactive(strength=(0.5, [0.0, 1.0]))
def denoise(img, strength=0.5):
    out = smooth(img, strength)
    layout.style("out", title=f"PSNR {psnr(out, img):.2f} dB")
    return out
```

The title follows each run on every backend (Gradio updates the component
label), in snapshots and in each cell of a [sweep](snapshots.md). `subtitle=`
appends a second part (`title · subtitle`). A filter returning a `str` gets a
text cell instead: written larger than the titles (12 pt) and wrapped to the
cell on every backend.

The heatmap options apply on every backend and in snapshots; on Qt the pixel readout still shows the raw value. NaN and masked values are shown in magenta. See [Figures, heatmaps and overlays](figures-and-overlays.md). An unknown colormap raises `ValueError` (with a suggestion), other unknown keys are ignored with a warning listing the supported ones.

## Image viewer (Qt, Dear PyGui)

On the Qt and Dear PyGui backends every image cell is a small image viewer, so large outputs stay usable:

- **Fit by default**: each image is scaled to its cell, keeping its aspect ratio, and rescales as you resize the window. Cells share the window space evenly, and the window can be shrunk below the native image size.
- **Wheel zoom** around the mouse cursor, **left-drag** to pan. Zooming out stops at the fit size, and the image stays centered along each axis where it fits; zoomed in, panning stops at the image edges.
- **Double-click** resets the view to fit.
- **Synced across cells**: zoom and pan are shared by all the images of the window, so a before/after comparison stays aligned while you inspect details.
- **Zoom level on hover**: hovering an image shows its zoom in the status line at the bottom of the window (`100%`: one image pixel per screen pixel; for a heatmap, per data pixel), updated as the wheel zooms.
- **Pixel values on hover** (Qt only): hovering an image shows the pixel coordinates and the value of the raw pipeline output (a float per channel for RGB, a scalar for grayscale) in the status line at the bottom of the window, not the 8-bit display value. Set `window.on_pixel_hover` to your own `(row, col, x, y, value)` callback, or to `None` to get the readout as a tooltip instead.
- **View menu / keys**: fit to window (++0++), actual size 100% (++1++), zoom in (++plus++), zoom out (++minus++). By default ++1++ zooms the images to 100% (one image pixel per screen pixel) inside their cells, the window keeps its size; wheel zoom and drag pan carry on from there. With `interactive_pipeline(..., actual_size="window")`, ++1++ instead grows the window so the images show whole at their native size (on Dear PyGui the sliders also move up when the images are smaller than their fitted size); going back to fit restores the previous window size. The controls below the images spread over several columns (in order, balanced heights) when they would not fit the height left by the images; on Qt the window grows wider for them, up to the screen width. In that mode the images always show whole at 1:1: when they and the controls still do not fit the screen, the images keep their place and the controls scroll in their own area below them (the window itself never scrolls). That area also scrolls in the fit view when the window is too small for the controls. Full-screen and maximized windows are not resized.

On Qt, zoomed-in pixels are drawn crisp (no interpolation) for pixel peeping; Dear PyGui interpolates them. Saving images (`w`) always writes the full-resolution results, whatever the current zoom.

## `layout` methods

::: interactive_pipe.core.context._LayoutProxy
    options:
      show_root_heading: false
      show_source: false
