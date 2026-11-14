---
name: build-interactive-pipeline
description: Build, modify, debug or check an interactive_pipe app — turn plain Python/numpy functions into a GUI with sliders, checkboxes and dropdowns (@interactive filters chained by an @interactive_pipeline function), tune image / signal / audio processing parameters, and check the result without a display (describe, snapshot and sweep to PNG, headless pipelines, INTERACTIVE_PIPE_SNAPSHOT, the interactive-pipe CLI). Use whenever code imports interactive_pipe, or the user wants a quick GUI or visual debugging for array processing.
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


@interactive_pipeline(gui="qt")  # or "dpg", "mpl", "nb", "gradio", "auto", None (headless)
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
- filter calls, assigned or not: `out = f(img)`, `a, b = f(img)`, `f(img)`, `gen()` (no input)
- nested calls `blur(amplify(img))` and `return amplify(img)` — the inner result is named after its source, `amplify(img)`
- literal keyword arguments `amplify(img, gain=2.5)`: sets that call's value and its widget default (validated against the range)
- dotted calls `np.abs(img)`, `lib.blur(img)`; names resolve in the function's real scope, so a pipeline may live inside `main()` or a test
- one final `return` of names, tuples, (nested) lists for a 2D grid, `None`, or calls

Rejected: `if` / `for` / `while` / `with` / `try`, arithmetic and any non-call expression (`img * 2`, `img[0]`), `+=`, comprehensions, lambdas, statements after `return`, `*args` / `**kwargs`, positional literals (`blur(img, 3)` → `blur(img, radius=3)`), variables as keyword values, builtins (`print`), unknown names (with "did you mean"). **Put logic inside filters**: give the filter a checkbox and branch there.

<!-- code: raises PipelineSyntaxError -->
```python
from interactive_pipe import interactive_pipeline


@interactive_pipeline(gui=None)
def wrong(img):
    if img.mean() > 0.5:  # PipelineSyntaxError: `if` statements are not supported
        img = img * 0.5
    return img
```

## Controls (declared in `@interactive(...)`)

| Widget | Declaration |
|---|---|
| Float slider | `gain=(1.0, [0.0, 3.0])` (optional 3rd item: label) |
| Int slider | `size=(5, [1, 15])` |
| Checkbox | `flip=False` / `flip=True` (or `flip=(True,)`) |
| Dropdown | `mode=("dark", ["dark", "light"])` or `mode=["dark", "light"]` |
| Explicit | `gain=Control(1.0, [0.0, 3.0], step=0.1, name="gain", group="Panel A", tooltip="...")` |
| Key-driven | `idx=KeyboardControl(0, [0, 2], keydown="pagedown", keyup="pageup", modulo=True)` |
| Text box | `txt=TextPrompt("hello")` |
| Low/high pair | `band=RangeControl((0.2, 0.8), [0.0, 1.0])` |
| Animation clock | `t=TimeControl(update_interval_ms=50)` (Qt and dpg; a slider elsewhere) |

Import them from `interactive_pipe`; group widgets with `group="name"` or a nestable `Panel`. The control default wins over the signature default; a keyword argument without a declaration gets no widget. A bare number in the decorator (`gain=1.0`) raises `ValueError`: a slider needs a range.

Same parameter in several filters: both `amplify` and `blend` declaring `gain` show as `amplify.gain` and `blend.gain`. `pipe(img, gain=2.0)` sets every filter's `gain`; target one with `"amplify.gain"` in `snapshot` / `sweep`, or `pipe(img, parameters={"amplify": {"gain": 2.0}})`.

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

numpy image (float `[0, 1]`, uint8, `(H, W)` gray or `(H, W, 3)`), 1D array (plotted), `Curve` / `SingleCurve` (plots), `Table`, `str` (text), or a tuple of those. The pipeline's `return` sets the display grid: a tuple or flat list is one row, a list of lists is a 2D grid, `None` leaves an empty cell.

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

`draw.*` functions are pure (new array, same dtype and range, gray promoted to RGB), take `(x, y)` pixel coordinates and clip marks outside the image. A filter may also return an `interactive_pipe.Image` (its `title` titles the cell). Heatmaps (2D arrays): `layout.style("err", colormap="RdBu_r", center=0, colorbar=True, unit="px")` draws the scale into the image, also in snapshots; NaN shows magenta.

## Proxies: context, layout, events, audio

<!-- code: continue -->
```python
from interactive_pipe import audio, context, events, layout


@interactive()
def analyse(img):
    context["mean"] = float(img.mean())  # shared with later filters: context.get("mean")
    noisy = events.get("noise_burst")  # True for one run after a key bound with bind_key_to_context
    layout.style("heat", title="Luma", colormap="viridis", vmin=0, vmax=1)  # 2D array as a heatmap
    layout.grid([["img", "amplified"], ["heat"]])  # optional: names of the pipeline's variables
    heat = img.mean(axis=-1) + (0.1 if noisy else 0.0)
    return heat  # audio.set("track.mp3"); audio.play() for sound (Qt)
```

Never add `global_params` / `context` / `state` parameters to a filter signature (removed in 0.9.0, `TypeError`). Seed the context with `@interactive_pipeline(context={...})`.

## Check your work without a display

You cannot see the window, but you can read a PNG. **Never call a visual change done without looking at a snapshot.**

1. **Describe**: `print(pipe.summary())` (or `pipe.describe()`, a JSON-friendly dict): inputs, outputs, filters, every control with range and value.
2. **Snapshot**: `pipe.snapshot("/tmp/out.png", img, gain=2.0)` renders what the window shows, parameter values in the caption. Overrides apply to this call only.
3. **Read the PNG** with your image-reading tool: black or clipped images, wrong colours, curves off-range, wrong layout?
4. **Adjust** the code or values, snapshot again.
5. **Sweep**: `pipe.sweep("/tmp/sweep.png", img, gain=[0.5, 1, 2])` (one row; two lists make a grid; `steps={"gain": 5}` spans the slider range) to choose defaults and ranges.

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
amplify.sweep("/tmp/amp_sweep.png", img, steps={"gain": 4})
```

- Unknown names raise `TypeError` listing the available ones; a parameter named like an option (`title`, `output`, `dpi`...) goes through `params={...}`. `path=None` returns the image as an array.
- Inputs can be omitted after the first call; `output="name"` / `"all"` picks what a sweep cell shows.
- Unmodified scripts: `interactive-pipe snapshot script.py -o /tmp/shots/` writes one PNG per pipeline call (`<pipeline>.png`, `<pipeline>_2.png`...) instead of opening a window, and prints the paths; `interactive-pipe describe script.py` prints the controls. Without the CLI, `INTERACTIVE_PIPE_SNAPSHOT=/tmp/shots/ python script.py` writes `<pipeline>.png` (a repeated call overwrites it).
- Set `MPLBACKEND=Agg` and `QT_QPA_PLATFORM=offscreen` so nothing opens a display.

## Headless use, saving, tuning

<!-- code: continue -->
```python
@interactive_pipeline(gui=None)  # gui=None (or "headless"): a HeadlessPipeline, no GUI at all
def batch(img):
    amplified = amplify(img)
    return img, amplified


original, amplified = batch(img, gain=2.0)  # call it like a function; later calls may omit img
written = batch.save("/tmp/res/result.png")  # every output + result.yaml; returns the paths
batch.export_tuning("/tmp/res/tuning.yaml")
batch.load_tuning("/tmp/res/tuning.yaml")
```

- `INTERACTIVE_PIPE_GUI=headless|qt|dpg|mpl|nb|gradio` overrides `gui="auto"`; `INTERACTIVE_PIPE_SIZE=1280x800|fullscreen|maximized`.
- `interactive_pipe.cli.parse_gui_args()` adds `--gui`, `--size`, `--fullscreen` to a script.
- `interactive-pipe doctor` lists installed backends, the pip extra for each missing one, whether a display is available and what `gui="auto"` picks: run it when "nothing shows up".

## Errors and fixes

| Message | Fix |
|---|---|
| `PipelineSyntaxError: pipeline 'p', file.py, line N: ...` | Follow its `Hint:` — usually move the logic or arithmetic into a filter |
| `PipelineSyntaxError: name 'x' is not defined ... did you mean` | Typo, or the filter is not defined / imported before the pipeline |
| `PipelineSyntaxError: positional literal arguments are not supported` | Pass it by keyword: `blur(img, radius=3)` |
| `TypeError: pipeline 'p' got unexpected keyword argument(s) 'gian'` | Use a name from the listed parameters |
| `ValueError: pipeline 'p' expects 1 input (img), got 0` | Pass every pipeline input (once; later calls reuse them) |
| `ValueError: @interactive(gain=1.0): a bare value cannot make a widget` | `gain=(1.0, [0.0, 2.0])`, or keep the default in the signature only |
| `ValueError: Cannot create a control from gain=(5, [0, 3]): min=5 max=[0, 3] ...` | The default is outside the range: fix one of them (`Control(5, [0, 3])` says `value_default 5 must be within value_range [0, 3]`) |
| `TypeError: Filter 'f' declares keyword argument 'global_params'` | Remove it, use `context` / `layout` |
| `Duplicate control name 'x'` | Two controls explicitly `name=`d alike in one pipeline: rename one |
| Log `Control 'gain': value 99.0 is outside its range ... clamped` | Widen the range or fix the value |
| `FilterError: Filter 'f' raised ValueError: ...` | Bug in that filter: the message shows its file and line |
| Control shows as `amplify.gain` | Not an error: two filters share `gain` (see Controls) |
| No window / crash on a server | Snapshot instead, or `gui=None`; `interactive-pipe doctor` |

## More

Docs: https://balthazarneveu.github.io/interactive_pipe/ — guides for controls, layout, curves, tables, keyboard, audio, panels, snapshots and the command line (`interactive-pipe --help`); the whole site as one text file: https://balthazarneveu.github.io/interactive_pipe/llms-full.txt
