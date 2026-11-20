---
name: build-interactive-pipeline
description: Build, modify, debug or check an interactive_pipe app — turn plain Python/numpy functions into a GUI with sliders, checkboxes and dropdowns (@interactive filters chained by an @interactive_pipeline function), tune image / signal / audio processing parameters, and check the result without a display (interactive-pipe check, describe, snapshot and sweep to PNG, headless pipelines, INTERACTIVE_PIPE_SNAPSHOT, the interactive-pipe CLI), click / drag input on images. Use whenever code imports interactive_pipe, or the user wants a quick GUI or visual debugging for array processing.
---

# Build and check an interactive_pipe pipeline

Filters are plain functions; `@interactive(...)` turns their keyword arguments into widgets; a pipeline function chains filters; `@interactive_pipeline(gui=...)` turns it into an app. Images are numpy arrays, float in `[0, 1]`, shape `(H, W, 3)` or `(H, W)`.

```python
import numpy as np
from interactive_pipe import interactive, interactive_pipeline


@interactive(gain=(1.0, [0.0, 3.0]), flip=False)  # a slider and a checkbox
def amplify(img, gain=1.0, flip=False):
    out = img * gain
    return out[::-1] if flip else out


@interactive(mix=(0.5, [0.0, 1.0]))
def blend(img0, img1, mix=0.5):
    return (1 - mix) * img0 + mix * img1


@interactive_pipeline(gui="qt")  # "dpg", "mpl", "nb", "gradio", None; default "auto": `python app.py -b mpl`
def my_pipeline(img):
    amplified = amplify(img)
    blended = blend(img, amplified)
    return amplified, blended  # displayed side by side, titled by variable name


x, y = np.meshgrid(np.linspace(0, 1, 192), np.linspace(0, 1, 128))
img = np.stack([x, y, 0.5 * np.ones_like(x)], axis=-1)  # (128, 192, 3) float image
my_pipeline(img)  # opens the window (blocks until it is closed)
```

## The pipeline body is parsed, never executed

Every top-level statement is checked when the decorator runs; anything else raises `PipelineSyntaxError` (a `ValueError`) with file, line, the source line and a `Hint:`. Accepted:

- docstring, `pass`, `...`
- filter calls, assigned or not: `out = f(img)`, `a, b = f(img)`, `f(img)` (its result is dropped), `gen()` (no input)
- nested calls `blur(amplify(img))` and `return amplify(img)` — the inner result is named after its source, `amplify(img)`
- literal keyword arguments `amplify(img, gain=2.5)`: sets that call's value and its widget default (validated against the range)
- dotted calls `np.abs(img)`, `lib.blur(img)`; names resolve in the function's real scope, so a pipeline may live inside `main()` or a test
- one final `return` of names, tuples, (nested) lists for a 2D grid, `None`, or calls

Rejected: `if` / `for` / `while` / `with` / `try`, arithmetic and any non-call expression (`img * 2`, `img[0]`), `+=`, comprehensions, lambdas, statements after `return`, `*args` / `**kwargs`, positional literals (`blur(img, 3)` → `blur(img, radius=3)`), variables as keyword values, builtins (`print`), unknown names (with "did you mean"). **Put logic inside filters**: give the filter a checkbox and branch there.

## Controls (declared in `@interactive(...)`)

| Widget | Declaration |
|---|---|
| Float slider | `gain=(1.0, [0.0, 3.0])` (optional 3rd item: label) |
| Int slider | `size=(5, [1, 15])` |
| Checkbox | `flip=False` / `flip=True` (or `flip=(True,)`) |
| Dropdown | `mode=("dark", ["dark", "light"])` or `mode=["dark", "light"]` |
| Explicit | `gain=Control(1.0, [0.0, 3.0], step=0.1, name="gain", group="Panel A", tooltip="...")` |
| Low/high pair | `band=RangeControl((0.2, 0.8), [0.0, 1.0])` |
| Animation clock | `t=TimeControl(update_interval_ms=50)` (Qt and dpg; a slider elsewhere) |

Import them from `interactive_pipe` (also `KeyboardControl`, `TextPrompt`: see the controls guide); group widgets with `group="name"` or a nestable `Panel`. Log slider: `lr=Control(1e-2, [1e-4, 1e-1], scale="log")`, `(1e-2, [1e-4, 1e-1, "log"])` or `Annotated[float, (1e-4, 1e-1, "log")]`; values, sweeps and captions are the real value. The control default wins over the signature default; a keyword argument without a declaration gets no widget. A bare number in the decorator (`gain=1.0`) raises `ValueError`: a slider needs a range.

Same parameter in several filters: both `amplify` and `blend` declaring `gain` (no label) show as **two** sliders, `amplify.gain` and `blend.gain`; a label (`Annotated[..., "label"]`, `name=`) is the control's name and must be unique, so the same label in two filters raises. `pipe(img, gain=2.0)` sets every filter's `gain`; target one with `"amplify.gain"` in `snapshot` / `sweep`, or `pipe(img, parameters={"amplify": {"gain": 2.0}})`. **One slider for several filters**: declare the control once and pass the same object to each decorator — `band = RangeControl((0.1, 0.3), [0.0, 0.7])`, then `@interactive(band=band)` on both filters (the parameter names may differ): one widget, one value (a shared checkbox: `Control(False, name="...")`).

## Controls from type hints

Alternative to decorator arguments: under `@interactive` (parentheses optional) the signature declares widgets and defaults.

<!-- code: continue -->
```python
from typing import Annotated, Literal


@interactive
def adjust(
    img,
    exposure: Annotated[float, (0.0, 3.0)] = 1.0,  # float slider: (min, max[, step]), then label, then group
    radius: Annotated[int, (1, 15, 2), "Blur radius"] = 3,  # int slider with a step and a label
    invert: Annotated[bool, "Invert"] = False,  # checkbox (the label is required)
    mode: Literal["dark", "light"] = "light",  # dropdown; an Enum hint works too (the filter gets the member)
):
    out = img * exposure * (0.5 if mode == "dark" else 1.0)
    return 1 - out if invert else out
```

Plain hints (`gain: float = 1.0`) make no widget; a decorator argument wins over the annotation; `Annotated[float, Control(...)]` takes any control class. A bad declaration raises at import, naming filter, parameter and fix.

## What a filter can return

numpy image `(H, W)`, `(H, W, 1)`, `(H, W, 3)` or RGBA `(H, W, 4)` (on a checkerboard) — float in `[0, 1]`, `uint8`, `uint16` or `bool` mask —, 1D array (plotted), `Curve`, `Table`, `Image` (an array with a cell title), `str` (a text cell), matplotlib `Figure` / `Axes`, or a tuple of those: every backend and the snapshots show them the same (2D arrays in gray). Other integer dtypes are taken as values (`check` warns); channel-first or 4D arrays raise `DisplayError` with the fix. **A returned tuple is unpacked** into the names the line assigns (`a, b = f(img)`); a returned list assigned to one name stays one value (a list of detections, even empty). The pipeline's `return` sets the display grid: a tuple or flat list is one row, a list of lists is a 2D grid, `None` leaves an empty cell.

<!-- code: continue -->
```python
from interactive_pipe import Curve, Image, SingleCurve, Table


@interactive()
def report(img):
    x = np.arange(img.shape[1])
    mean = SingleCurve(x, img.mean(axis=(0, 2)), style="b-", label="mean", linewidth=1)  # or [x, y, "b-", "mean"]
    profile = Curve([mean], xlabel="column", ylim=(0, 1), grid=True)  # also ylabel, title, xlim, xscale / yscale="log"
    table = Table([{"stat": "mean", "value": img.mean()}], title="stats", precision=3)  # or a dict of lists / arrays
    return profile, table, Image(img, title=f"mean {img.mean():.3f}")  # a metric in the title, not a text cell
```

`SingleCurve(x, y, style=, label=, linestyle=, linewidth=, markersize=, alpha=)`; `Curve(..., yscale="log")` (`"linear"`, `"log"`, `"symlog"`); in tests `table.columns` and `table.values` (rows of formatted cells).

## Figures and overlays

<!-- code: continue -->
```python
from matplotlib.figure import Figure  # never pyplot: no global state, no leaked figures
from interactive_pipe import draw


@interactive(threshold=(0.5, [0.0, 1.0]))
def detect(img, threshold=0.5):
    ys, xs = np.nonzero(img.mean(axis=-1) > threshold)
    boxes = [(xs.min(), ys.min(), xs.max(), ys.max())] if len(xs) else []  # x0, y0, x1, y1 in pixels
    return draw.boxes(img, boxes, labels=["bright"] * len(boxes))  # also draw.points / lines / polygon / text / mask


@interactive()
def histogram(img):
    fig = Figure(figsize=(4, 3))
    fig.subplots().hist(img.ravel(), bins=32)
    return fig  # a Figure or an Axes: rasterised identically on every backend and in snapshots
```

`draw.*` functions are pure (new array, same dtype and range, gray promoted to RGB), take `(x, y)` pixel coordinates and clip marks outside the image; `color=` takes one colour or a list (one per mark), `draw.lines(img, segments)` takes `(K, 2, 2)` segments, `draw.points(img, xy, radius=6, filled=False)` draws circles, `draw.mask(img, mask, color=, alpha=0.5)` blends a mask. Heatmaps (2D arrays): `layout.style("err", colormap="RdBu_r", center=0, colorbar=True)` draws the scale into the image, also in snapshots; NaN shows magenta; `unit="px"` is written once above the bar, `colorbar="a longer label"` along it; `extent=(x_left, x_right, y_bottom, y_top), xlabel=, ylabel=` draws axes with round ticks (the Qt readout shows those coordinates). A figure is drawn at the size of its cell (its text is the size of a `Curve`'s): `figsize` only sets the aspect ratio. Zero marks (`draw.boxes(img, [])`) and an empty `Table` are fine. Readout next to an output: `layout.style("out", title=f"PSNR {psnr:.2f} dB")`. Calls on one output in a run add up (a later `title=` keeps the colormap; `key=None` removes a key); any displayed name can be styled, a pipeline input included.

## Mouse input: a point or a region on an image

<!-- code: continue -->
```python
from interactive_pipe import PointControl, RegionControl, to_pixels


@interactive(seed=PointControl((0.5, 0.5)), roi=RegionControl((0.25, 0.25, 0.75, 0.75), on="img"))
def inspect(img, seed=(0.5, 0.5), roi=(0.25, 0.25, 0.75, 0.75)):
    col, row = to_pixels(seed, img)  # fractions of the image size, (0, 0) = top-left -> pixels
    x0, y0, x1, y1 = to_pixels(roi, img)  # img[y0:y1, x0:x1] is never empty
    return draw.points(img, [(col, row)]), img[y0:y1, x0:x1]


inspect.snapshot("/tmp/inspect.png", img, seed=(0.2, 0.4))  # headless: a plain tuple parameter
```

- Click sets the nearest point, shift + drag draws a region (Qt, dpg, mpl; Gradio: click only; notebook: sliders); the window draws the marker, snapshots do not (use `draw` if it must be in the output).
- `on=` names the displayed output receiving the gesture (default: the first image); an unknown name raises when a GUI pipeline is built (a `gui=None` test pipeline only warns).
- Headless it is a plain tuple parameter: `pipe(img, seed=(0.2, 0.4))`, `sweep(..., seed=[(0.1, 0.1), (0.6, 0.4)])`, `--set seed=0.2,0.4`.

**Video (a timeline for a sequence of frames)**: keep the pipeline written for **one frame** and call it with `Video(source)`: the window gets a timeline (Qt film strip, play / pause with space, step with the arrows), filters get the current frame; never write a frame-selector filter or a loop. Sources: `"clip.mp4"` (OpenCV), a folder / glob / list of image paths, a numpy array `(T, H, W[, C])`, a torch tensor `(T, C, H, W)` (`to_numpy=False` keeps tensors), a generator (`max_frames=`); options `fps=`, `start=`, `stop=`, `step=`. The timeline is a control named `frame`: `pipe(Video(x), frame=20)`, `pipe.snapshot(path, Video(x), frame=10)`, `pipe.sweep(path, Video(x), frame=[0, 20, 40])`; `context["timeline"]` has `frame`, `time`, `fps`, `n_frames`. Temporal filters: `Video(x, window=3)` gives `(3, H, W[, C])`; pass `pipe(Video(x), Video(x, window=3))` for frame + window. Several videos share one timeline (matched by time). Other file formats (DNG, custom raw): `Video("raw/*.dng", loader=read_dng)` with `read_dng(path) -> frame` or `-> (frame, metadata_dict)`; a format holding many frames: subclass `FrameSource` (`__len__`, `read(i)`, `metadata(i)`); filters read the frame's metadata as `context["timeline"].metadata`; `preview=` maps frames that are not displayable (raw, 10-bit) to film strip thumbnails; `thumbnail_loader=read_preview` (files) or `FrameSource.thumbnail(i)` gives a cheap thumbnail (embedded JPEG) so the strip never decodes full frames. The windows decode `preload=8` frames ahead in the background (`preload=0` turns it off). `Video(x, timeline="collapsible" | "collapsed" | "hidden")` folds or hides the panel.

## Proxies: context, layout, events, audio

<!-- code: continue -->
```python
from interactive_pipe import context, layout


@interactive()
def analyse(img):
    context["mean"] = float(img.mean())  # shared with later filters: context.get("mean")
    layout.style("heat", title="Luma", colormap="viridis", vmin=0, vmax=1)  # 2D array as a heatmap
    layout.grid([["img", "amplified"], ["heat"]])  # optional: names of the pipeline's variables
    return img.mean(axis=-1)
```

`events.get("name")` (keys bound with `bind_key_to_context`) works the same way. Sound (Qt, Gradio): `audio.set("file.wav")` or `audio.set(signal, 16000)` (numpy, mono or `(n, 2)`, float in `[-1, 1]` or int16), then `audio.play()`; each `set` restarts from the beginning; headless it does nothing. A filter reading a context key re-runs whenever the earlier filter writing it does (every `cache=` mode). Never add `global_params` / `context` / `state` parameters to a filter signature (removed in 0.9.0, `TypeError`). Seed the context with `@interactive_pipeline(context={...})`. **Stateful simulations**: a state advanced in `context` on every run makes snapshots and sweep cells depend on the runs before (cells are not independent); make the output a function of the controls (a `TimeControl`'s `t` included, `snapshot(None, t=4.0)`) and use the context only as a cache keyed on them.

## Check your work without a display

You cannot see the window, but you can read a PNG. **Never call a visual change done without looking at a snapshot.**

0. **Check after every edit**: `interactive-pipe check script.py` runs every pipeline once without a window and prints, on one screen, its controls, each output's shape / dtype / range, the warnings (misleading outputs, clamped values) and the errors with file and line; exit code 1 on error, `--json` for a dict.
1. **Describe**: `print(pipe.summary())` (or `pipe.describe()`, a JSON-friendly dict): inputs, outputs, filters, every control with range and value.
2. **Snapshot**: `pipe.snapshot("/tmp/out.png", img, gain=2.0)` renders what the window shows, parameter values in the caption. Overrides apply to this call only.
3. **Read the PNG** with your image-reading tool: black or clipped images, wrong colours, curves off-range, wrong layout? Adjust, snapshot again.
4. **Sweep**: `pipe.sweep("/tmp/sweep.png", img, gain=[0.5, 1, 2])` (one cell per value, laid out to fit; two lists make a grid; `steps={"gain": 5}` spans the slider range) to choose defaults and ranges.

<!-- code: continue -->
```python
@interactive_pipeline(gui="qt")  # works with any gui=: these calls never open a window
def pipe(img):
    amplified = amplify(img)
    heat = analyse(amplified)
    return img, amplified, heat


print(pipe.summary())
pipe.snapshot("/tmp/out.png", img, gain=2.0)
pipe.sweep("/tmp/sweep.png", img, gain=[0.5, 1.0, 2.0], output="amplified")
amplify.snapshot("/tmp/amp.png", img, gain=2.0)  # one @interactive filter, no pipeline needed
report.snapshot("/tmp/report.png", img)  # curve, table and titled image side by side
```

- Unknown names raise `TypeError` listing the available ones; a parameter named like an option (`title`, `output`, `dpi`...) goes through `params={...}`. `path=None` returns the image as an array.
- Inputs can be omitted after the first call; `output="name"`, `["a", "b"]` or `"all"` picks what a snapshot or a sweep cell shows (default: a snapshot shows the whole layout, a sweep cell the first image the swept parameters change). Sweeps take any value a control takes: tuples for a `RangeControl`, strings for a dropdown.
- Unmodified scripts: `interactive-pipe snapshot script.py -o /tmp/shots/ --set t=4 --set mode=dark` writes one PNG per pipeline call (`<pipeline>.png`, `<pipeline>_2.png`...) instead of opening a window; `interactive-pipe sweep script.py --param gain=0.5,1,2 [--param mode=dark,light] --output out -o /tmp/sweep.png` makes a contact sheet (`--output` takes a name, `a,b` or `all`); `interactive-pipe describe script.py` prints the controls. Values are typed by the control (`seed=0.2,0.4` for a point; swept ranges / points are `;`-separated); unknown names fail with the list. Without the CLI, `INTERACTIVE_PIPE_SNAPSHOT=/tmp/shots/ python script.py` writes `<pipeline>.png`.
- Set `MPLBACKEND=Agg` and `QT_QPA_PLATFORM=offscreen` so nothing opens a display.

## Headless use, saving, tuning

<!-- code: continue -->
```python
@interactive_pipeline(gui=None)  # gui=None (or "headless"): a HeadlessPipeline, no GUI at all
def batch(img):
    amplified = amplify(img)
    return img, amplified


original, amplified = batch(img, gain=2.0)  # call it like a function (one output: a 1-tuple); later calls may omit img
written = batch.save("/tmp/res/result.png")  # every output + result.yaml; returns the paths
batch.export_tuning("/tmp/res/tuning.yaml")  # and load_tuning(...)
```

## Testing your filters

A decorated filter stays a plain function: `amplify(img, gain=2.0)` returns the array, also when it calls `layout` (ignored) or `context` (a scratch dict for that call). `my_pipeline.headless(img, gain=2.0)` returns the outputs of a pipeline decorated with any `gui=` as a tuple in `return` order (whatever `layout.grid` displays); `snapshot(None, ...)` returns the rendered RGB array; `my_pipeline.headless.styles["out"]["title"]` reads a readout title of the last run. Snapshots and sweeps start from a fresh `context` (`runs=N` to warm up a stateful pipeline). Run `interactive-pipe check script.py` in CI.

<!-- code: continue -->
```python
def test_amplify():
    assert np.allclose(amplify(img, gain=2.0), 2 * img)  # a plain call

    @interactive_pipeline(gui=None)
    def under_test(img):
        amplified = amplify(img)
        return amplified

    (amplified,) = under_test(img, gain=2.0)  # one output: a 1-tuple
    assert np.allclose(amplified, 2 * img)
    assert under_test.snapshot(None, img).std() > 0  # something is drawn


test_amplify()
```

## Errors and fixes

| Message | Fix |
|---|---|
| `PipelineSyntaxError: pipeline 'p', file.py, line N: `if` statements are not supported ...` | Follow its `Hint:` — usually move the logic or arithmetic into a filter |
| `TypeError: pipeline 'p' got unexpected keyword argument(s) 'gian'. Available parameters: gain ... Did you mean 'gian' -> 'gain'?` | Use a name from the list |
| `ValueError: @interactive(gain=1.0): a bare value cannot make a widget, a range is needed` | `gain=(1.0, [0.0, 2.0])`, or keep the default in the signature only |
| `ValueError: @interactive filter 'f', parameter 'gain': ... the default 5 is outside the range [0, 3]` | Choose a default inside the range, or widen it |
| Log `Control 'gain': value 9.0 is outside its range [0.0, 2.0], clamped to 2.0` | Widen the range or fix the value |
| `FilterError: Filter 'f' raised ValueError: ...` + `Traceback (user code only)` | Bug in that filter, at the file and line shown |
| `filter 'f' returned 3 values but the pipeline assigns 1 name(s)` | Unpack them (`a, b, c = f(img)`); a returned list, unlike a tuple, is kept as one value |
| `DisplayError: output 'out' (returned by filter 'f') cannot be displayed: channel-first array (3, 8, 8). Fix: ...` | Apply the `Fix:` (`np.moveaxis(img, 0, -1)`) |
| Log `output 'out' is displayed misleadingly: int64 image in [127, 127] ... Fix: ...` | Scale to `[0, 1]`, or `astype(np.uint8)` for 0-255 data |
| `RuntimeError: layout.style('x', ...) called outside of filter execution` | Call it inside a filter (a direct call of the filter is fine) |
| No window / crash on a server | `interactive-pipe check` / snapshot instead, or `gui=None`; `interactive-pipe doctor` (installed backends, display, what `gui="auto"` picks) |

## More

Docs: https://balthazarneveu.github.io/interactive_pipe/ — guides for controls, layout, curves, tables, keyboard, audio, panels, snapshots and the command line (`interactive-pipe --help`); the whole site as one text file: https://balthazarneveu.github.io/interactive_pipe/llms-full.txt. Teaching demos (caching, animation, GIF export, a quality bar for lessons): `showreel/lesson_guide.md` and `showreel/demos/` in the repository.
