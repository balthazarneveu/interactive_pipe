# Mouse input: points and regions

Scientific debugging often needs "this pixel" or "this region": the seed of a
region growing, the row whose profile is plotted, the patch whose spectrum is
shown, a crop to zoom on. Two controls give them with the mouse instead of
two or four sliders:

| Control | Value | Gesture |
|---|---|---|
| `PointControl((x, y), on="img")` | `(x, y)` | click on the image |
| `RegionControl((x0, y0, x1, y1), on="img")` | `(x0, y0, x1, y1)` | ++shift++ + drag on the image |

```python
import numpy as np

from interactive_pipe import PointControl, RegionControl, interactive, interactive_pipeline, to_pixels


@interactive(seed=PointControl((0.5, 0.5), on="img"))
def row_profile(img, seed=(0.5, 0.5)):
    col, row = to_pixels(seed, img)  # the pixel under the click
    return img[row, :, 0]  # a 1D array is shown as a curve


@interactive(roi=RegionControl((0.25, 0.25, 0.75, 0.75), on="img"))
def crop(img, roi=(0.25, 0.25, 0.75, 0.75)):
    x0, y0, x1, y1 = to_pixels(roi, img)
    return img[y0:y1, x0:x1]


@interactive_pipeline(gui="qt")
def pointer_pipeline(img):
    profile = row_profile(img)
    zoomed = crop(img)
    return [img, zoomed, profile]


pointer_pipeline(np.random.rand(120, 160, 3))
```

`demo/pointer_demo.py` is a complete example (row profile + enlarged crop).

## Coordinates: fractions of the image size

Values are **fractions of the image size in [0, 1]**, `(0, 0)` being the
top-left corner and `(1, 1)` the bottom-right one. A tuning file stays valid
when the resolution changes, and the value means something before any image
exists. In the filter, `to_pixels(value, img)` converts:

- a point `(x, y)` to `(col, row)`, the pixel under it (clipped into the
  image): `img[row, col]`;
- a region `(x0, y0, x1, y1)` to pixel bounds such that `img[y0:y1, x0:x1]`
  is the region, never empty (at least one pixel wide and tall).

`img` can also be a shape: `to_pixels(seed, (height, width))`.

<!-- code: continue -->
```python
assert to_pixels((0.5, 0.5), (100, 200)) == (100, 50)
assert to_pixels((0.25, 0.25, 0.75, 0.75), (100, 200)) == (50, 25, 150, 75)
```

Validation: a value with the wrong number of elements, a non-number or a
coordinate outside [0, 1] raises (`ValueError` / `TypeError`, naming the
control). A region given the other way round (`x1 < x0` or `y1 < y0`, as a
drag from bottom-right to top-left produces) is reordered.

## The target output: `on=`

`on="img"` names the pipeline output that receives the gestures, here the
input image itself; any variable of the pipeline body that is displayed works.
Without `on=`, the first image output is used. An unknown name fails when the
GUI is built (and in `describe()`), listing the available outputs.

A heatmap shown with a colorbar (`layout.style(..., colorbar=True)`) or
enlarged maps back to data pixels; clicks on the colorbar are ignored. A
matplotlib figure output cannot be a target (a warning says so).

## Gestures per backend

| Backend | Point | Region |
|---|---|---|
| Qt | click (moving less than 3 screen pixels) | ++shift++ + drag |
| Dear PyGui | click | ++shift++ + drag |
| matplotlib | click | ++shift++ + drag |
| Gradio | click on the image | sliders |
| notebook | sliders | sliders |

- A left drag without ++shift++ keeps panning the image (Qt, Dear PyGui);
  zoom and pan are taken into account.
- With several point controls on one image, a click moves the nearest one.
- The window draws the marker (a cross) and the rectangle, with the control
  names, over the image. The filter outputs are never modified, so snapshots
  show only what the filters draw (use [`draw`](figures-and-overlays.md) for
  marks that belong in the output).
- ++f1++ lists the gestures with the other shortcuts.
- Where gestures are not available, each control is shown as sliders in
  [0, 1]: `seed x`, `seed y` / `roi x0`, `roi y0`, `roi x1`, `roi y1`. This is
  also what a new backend gets until it implements gestures
  (`InteractivePipeGUI.pointer_gestures`).

## Headless: just a parameter

Everywhere else a point or a region is an ordinary parameter:

<!-- code: continue -->
```python
@interactive_pipeline(gui=None)
def headless_pipeline(img):
    profile = row_profile(img)
    zoomed = crop(img)
    return [img, zoomed, profile]


img = np.random.rand(120, 160, 3)
img_out, zoomed, profile = headless_pipeline(img, seed=(0.2, 0.4), roi=(0.0, 0.0, 0.5, 0.5))
assert zoomed.shape == (60, 80, 3)
headless_pipeline.sweep("/tmp/seeds.png", img, seed=[(0.1, 0.1), (0.6, 0.4)], output="profile")
print(headless_pipeline.summary())
```

- `pipe(img, seed=(0.2, 0.4))`, `snapshot`, `sweep(seed=[(0.1, 0.1), (0.6, 0.4)])`
  (a list of tuples is swept, a tuple is one value);
- `describe()` reports `kind: "point"` / `"region"`, `on` (the target output,
  `None` for the first image) and the `axes` names;
- tuning files store the value as a list (`seed: [0.2, 0.4]`).

It also works as an annotation:

<!-- code: continue -->
```python
from typing import Annotated, Tuple


@interactive()
def probe(img, seed: Annotated[Tuple[float, float], PointControl((0.5, 0.5))] = (0.5, 0.5)):
    col, row = to_pixels(seed, img)
    return img[row]
```
