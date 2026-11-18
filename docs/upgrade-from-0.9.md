# Upgrading from 0.9

The next release turns many silent mistakes into errors raised when the
pipeline is built or run, with the file, the line and the fix. Code that was
correct keeps working; code that only *looked* like it worked may now raise.
This page lists every behaviour change of the [changelog](changelog.md)
("Unreleased") with the code before and after.

Quick way to find what changed for your project: run each script once with
`interactive-pipe check my_script.py` ([command line](guide/command-line.md#check-run-after-every-edit)):
it builds and runs every pipeline without opening a window and lists the
errors with their file and line.

Every "after" block on this page runs in the test suite, and every "before"
block marked *raises* is checked to raise that exception now.

## Pipeline function body

### Only filter calls are allowed

The body of a pipeline function is parsed, not executed. 0.9 flattened it
silently: both branches of an `if` were always taken, a loop body ran once,
arithmetic was dropped (the pipeline could return `()`). Every top-level
statement is now validated and anything else raises `PipelineSyntaxError` (a
`ValueError`, exported from `interactive_pipe`) when the decorator runs.

Before (now raises `PipelineSyntaxError: ... `if` statements are not supported in a pipeline function`):

<!-- code: raises PipelineSyntaxError -->
```python
import numpy as np
from interactive_pipe import interactive, interactive_pipeline


@interactive(gain=(1.0, [0.0, 2.0]))
def amplify(img, gain=1.0):
    return img * gain


@interactive_pipeline(gui=None)
def pipe(img):
    out = amplify(img)
    if out.mean() > 0.5:
        out = out * 0.5
    return out
```

After: the condition, and any arithmetic, move into a filter (give it a
checkbox if it must be switchable).

```python
import numpy as np
from interactive_pipe import interactive, interactive_pipeline


@interactive(gain=(1.0, [0.0, 2.0]), dim=True)
def amplify(img, gain=1.0, dim=True):
    out = img * gain
    return out * 0.5 if dim and out.mean() > 0.5 else out


@interactive_pipeline(gui=None)
def pipe(img):
    out = amplify(img)
    return out


(out,) = pipe(np.full((4, 4), 0.4), gain=2.0)
assert np.allclose(out, 0.4)
```

Also rejected, each with a hint: `for` / `while` / `with` / `try`, `b = a * 2`
and any non-call expression, `+=`, comprehensions, lambdas, statements after
the `return`, `*args` / `**kwargs`, positional literals (`blur(img, 3)`: write
`blur(img, radius=3)`), builtins (`print`).

### Names are checked when the pipeline is built

An undefined variable (`offset(amplifed)`), a filter call missing a required
input, a method called on a pipeline variable (`img.copy()`), an unknown
filter name or a non-callable now raise `PipelineSyntaxError` at the line,
with a "did you mean". In 0.9 they failed on the first run (`KeyError`,
`missing a required argument`), silently used a module-level name, or raised
`KeyError` / `TypeError` at build time.

Before (now raises `PipelineSyntaxError: ... 'amplifed' ... did you mean 'amplified'?`):

<!-- code: raises PipelineSyntaxError -->
```python
from interactive_pipe import interactive, interactive_pipeline


@interactive()
def offset(img):
    return img + 0.1


@interactive_pipeline(gui=None)
def pipe(img):
    amplified = offset(img)
    out = offset(amplifed)  # typo
    return out
```

After: fix the name. Code catching `KeyError` / `TypeError` around a
pipeline definition should catch `PipelineSyntaxError` (or `ValueError`):

```python
from interactive_pipe import PipelineSyntaxError, interactive, interactive_pipeline


@interactive()
def offset(img):
    return img + 0.1


try:

    @interactive_pipeline(gui=None)
    def pipe(img):
        out = unknown_filter(img)  # noqa: F821
        return out

except PipelineSyntaxError as error:  # was KeyError in 0.9
    print(error)
```

### Keyword arguments in filter calls are applied or rejected

`amplify(img, gain=2.5)` in a pipeline body was ignored in 0.9. A literal value
now sets that call's parameter and its control's default (validated against
the range); a keyword that is not a parameter of the filter, or a variable as
value, raises `PipelineSyntaxError`.

Before (now raises `PipelineSyntaxError`: a variable is not a literal value):

<!-- code: raises PipelineSyntaxError -->
```python
from interactive_pipe import interactive, interactive_pipeline

GAIN = 2.5


@interactive(gain=(1.0, [0.0, 3.0]))
def amplify(img, gain=1.0):
    return img * gain


@interactive_pipeline(gui=None)
def pipe(img):
    out = amplify(img, gain=GAIN)
    return out
```

After: a literal (`amplify(img, gain=2.5)`), or the value in the control's
declaration. Check that the keywords you had written were meant: they now
take effect.

```python
import numpy as np
from interactive_pipe import interactive, interactive_pipeline


@interactive(gain=(1.0, [0.0, 3.0]))
def amplify(img, gain=1.0):
    return img * gain


@interactive_pipeline(gui=None)
def pipe(img):
    out = amplify(img, gain=2.5)  # applied (was ignored in 0.9)
    return out


(out,) = pipe(np.ones((2, 2)))
assert np.allclose(out, 2.5)
```

### A filter must return what the line assigns

A filter returning more values than its pipeline line assigns (`a = f(x)` with
`return x, y`) kept the first value(s) silently; it now raises `FilterError`
naming the line and the fix. A filter without any `return <value>` whose
result is assigned raises likewise (an explicit `return None` is accepted).
`FilterCore` lists built by hand keep the old behaviour.

Before (now raises `FilterError: ... returned 2 values but the pipeline assigns 1 name(s)`):

<!-- code: raises FilterError -->
```python
import numpy as np
from interactive_pipe import interactive, interactive_pipeline


@interactive()
def split(img):
    return img[:, :2], img[:, 2:]


@interactive_pipeline(gui=None)
def pipe(img):
    left = split(img)
    return left


pipe(np.ones((4, 4)))
```

After: unpack every value, or return a tuple as one value with
`return (values,)` (a list is always one value, see the next section):

```python
import numpy as np
from interactive_pipe import interactive, interactive_pipeline


@interactive()
def split(img):
    return img[:, :2], img[:, 2:]


@interactive_pipeline(gui=None)
def pipe(img):
    left, right = split(img)
    return left, right


left, right = pipe(np.ones((4, 4)))
```

### A list assigned to one name stays a list

`dets = detect(img)` receives the list the filter returned, whatever its
length. Before, a 1-item list silently became its item, and an empty or longer
list raised. Several names (`a, b = f(img)`) still unpack a list, and tuples
keep their rule (previous section). Nothing to change unless a filter relied on
a 1-item list being unwrapped: return the item itself.

```python
import numpy as np
from interactive_pipe import interactive, interactive_pipeline


@interactive(count=(1, [0, 5]))
def detect(img, count=1):
    return [{"x": k, "y": k} for k in range(count)]  # 0, 1 or more detections


@interactive()
def report(detections):
    return f"{len(detections)} detection(s)"


@interactive_pipeline(gui=None)
def pipe(img):
    detections = detect(img)
    text = report(detections)
    return text


for count in (0, 1, 3):
    (text,) = pipe(np.ones((4, 4)), count=count)
    if text != f"{count} detection(s)":
        raise RuntimeError(text)
```

## Calling a pipeline

### Unknown keyword arguments and `parameters={...}` raise

`pipe(img, gian=2.0)` was ignored in 0.9; it now raises `TypeError` listing the
parameters with a close match (headless and GUI pipelines). An unknown filter
or parameter in `parameters={...}` raises `ValueError` before anything is
applied (0.9 stored it and every later run failed inside the filter).

Before (now raises `TypeError: pipeline 'pipe' got unexpected keyword argument(s) 'gian' ... Did you mean 'gian' -> 'gain'?`):

<!-- code: raises TypeError -->
```python
import numpy as np
from interactive_pipe import interactive, interactive_pipeline


@interactive(gain=(1.0, [0.0, 3.0]))
def amplify(img, gain=1.0):
    return img * gain


@interactive_pipeline(gui=None)
def pipe(img):
    out = amplify(img)
    return out


pipe(np.ones((2, 2)), gian=2.0)
```

After: the names from the message; `"filter.parameter"` targets one filter.

```python
import numpy as np
from interactive_pipe import interactive, interactive_pipeline


@interactive(gain=(1.0, [0.0, 3.0]))
def amplify(img, gain=1.0):
    return img * gain


@interactive_pipeline(gui=None)
def pipe(img):
    out = amplify(img)
    return out


pipe(np.ones((2, 2)), gain=2.0)
pipe(np.ones((2, 2)), **{"amplify.gain": 2.0})
pipe(np.ones((2, 2)), parameters={"amplify": {"gain": 2.0}})
```

### Two filters declaring the same control name

Two filters declaring an auto-named `gain` in one pipeline raised
`Duplicate control name` in 0.9. They now get two widgets, `amplify.gain` and
`blend.gain` (a repeated filter's copy is `amplify_1.gain`); explicitly named
(`name=...`) collisions still raise. `pipe(img, gain=2.0)` sets both.

```python
import numpy as np
from interactive_pipe import interactive, interactive_pipeline


@interactive(gain=(1.0, [0.0, 3.0]))
def amplify(img, gain=1.0):
    return img * gain


@interactive(gain=(0.5, [0.0, 1.0]))
def blend(img0, img1, gain=0.5):
    return (1 - gain) * img0 + gain * img1


@interactive_pipeline(gui=None)
def pipe(img):
    amplified = amplify(img)
    out = blend(img, amplified)
    return out


print([control.name for control in pipe.controls])  # ['amplify.gain', 'blend.gain']
pipe(np.ones((2, 2)), parameters={"blend": {"gain": 1.0}})  # one filter only
```

### `HeadlessPipeline.save()` returns the written files

It returned the base path; it now returns the list of files written (one per
output, by type: images, `.csv` for 1D arrays, `.npy`, curves, tables, figures,
text). Code using the return value as the base path should keep its own:

```python
import numpy as np
from interactive_pipe import interactive, interactive_pipeline


@interactive()
def double(img):
    return np.clip(img * 2, 0, 1)


@interactive_pipeline(gui=None)
def pipe(img):
    out = double(img)
    return out


pipe(np.full((4, 4, 3), 0.25))
written = pipe.save("/tmp/result.png")  # [PosixPath('/tmp/result_out.png')], was the base path
```

### `layout.grid` no longer changes what a call returns

A filter calling `layout.grid([...])` used to turn the result of later
pipeline calls into the grid's list of rows, in the grid's order. Calls,
`.headless(...)` and `save()` now follow the pipeline function's `return`;
the window and snapshots still show the grid:

```python
import numpy as np
from interactive_pipe import interactive, interactive_pipeline, layout


@interactive()
def half(img):
    layout.grid([["out", "img"]])  # display: out first
    return img * 0.5


@interactive_pipeline(gui=None)
def pipe(img):
    out = half(img)
    return img, out


img, out = pipe(np.ones((4, 4)))  # was [[out, img]]
assert out[0, 0] == 0.5
```

### A bare filter call drops its result

`f(img)` on its own line of a pipeline body (the result not assigned) raised
`filter 'f' returned a single ndarray but the pipeline unpacks 0 values` when
`f` returned something. The filter now runs and its result is dropped, as in
Python:

```python
import numpy as np
from interactive_pipe import interactive, interactive_pipeline


@interactive()
def log_stats(img):
    print(f"mean {img.mean():.2f}")
    return img.mean()  # ignored by the line below


@interactive_pipeline(gui=None)
def pipe(img):
    log_stats(img)
    return img


pipe(np.ones((4, 4)))
```

### An unknown `on=` target only warns without a window

A `PointControl` / `RegionControl` whose `on=` names an output the pipeline
does not produce raised when any pipeline was built. A GUI pipeline still
raises (at decoration, and when a GUI is built); a `gui=None` pipeline and
`describe()` now log a warning instead (no mouse there: the control keeps its
value), so a small test pipeline can reuse the filter:

```python
import numpy as np
from interactive_pipe import PointControl, interactive, interactive_pipeline


@interactive(seed=PointControl((0.5, 0.5), on="overlay"))
def probe(img, seed=(0.5, 0.5)):
    return img[int(seed[1] * (img.shape[0] - 1))]


@interactive_pipeline(gui=None)  # no 'overlay' here: a warning, not an error
def under_test(img):
    row = probe(img)
    return row


(row,) = under_test(np.eye(3))
```

### `graph_representation()` writes an HTML page

It rendered a graphviz diagram (PDF by default) and returned the
`graphviz.Digraph`, or logged install instructions when graphviz was missing.
It now writes a standalone HTML page (inline SVG, no dependency) and returns
its `Path`; a path without suffix gets `.html`. The graphviz rendering is kept
for `format="pdf"` / `"svg"` / `"png"` (or a path ending with that suffix):

```python
import numpy as np
from interactive_pipe import interactive, interactive_pipeline


@interactive(gain=(1.0, [0.0, 2.0]))
def amplify(img, gain=1.0):
    return img * gain


@interactive_pipeline(gui=None)
def pipe(img):
    out = amplify(img)
    return out


path = pipe.graph_representation("/tmp/pipe")  # /tmp/pipe.html, was a graphviz PDF
assert path.suffix == ".html" and "amplify" in path.read_text()
# pipe.graph_representation("/tmp/pipe", format="pdf")  # graphviz, as before
```

## Declaring controls

### A bare value in `@interactive` raises

`@interactive(gain=1.0)` created no widget and said nothing; it now raises
`ValueError` explaining that a slider needs a range (a bare string needs a
list of choices). Plain defaults in the signature still mean "no widget".

Before (now raises `ValueError: @interactive(gain=1.0): a bare value cannot make a widget, a range is needed`):

<!-- code: raises ValueError -->
```python
from interactive_pipe import interactive


@interactive(gain=1.0)
def amplify(img, gain=1.0):
    return img * gain
```

After:

```python
from interactive_pipe import interactive


@interactive(gain=(1.0, [0.0, 2.0]))  # a slider
def amplify(img, gain=1.0):
    return img * gain


@interactive()
def offset(img, shift=0.1):  # no widget: a plain default
    return img + shift
```

### Stricter control declarations

`Control` rejects a step `<= 0` or larger than the range, `min > max`
(`min == max` is allowed) and a range with more than `[min, max, step]`
(`ValueError`); a `bool` given to a numeric control raises `TypeError` (it was
taken as 0 / 1); `layout.style(..., vmin=, vmax=, center=, dpi=)` values must
be numbers (`TypeError`). Errors name the filter and the parameter.

Before (now raises `ValueError`: the step is larger than the range):

<!-- code: raises ValueError -->
```python
from interactive_pipe import Control

Control(0.5, [0.0, 1.0], step=2.0)
```

After:

```python
from interactive_pipe import Control

Control(0.5, [0.0, 1.0], step=0.1)
```

### `Literal` and `Enum` hints make dropdowns

Under `@interactive`, a parameter with a default and a `Literal[...]` or
`Enum` hint now gets a dropdown (the filter receives the value, or the Enum
member). Other annotations make widgets only through `Annotated[...]`
([controls from type hints](guide/controls.md#controls-from-type-annotations)).
Remove the hint (or use `str`) if no widget is wanted.

```python
from typing import Literal

import numpy as np
from interactive_pipe import interactive


@interactive
def tone(img, mode: Literal["dark", "light"] = "light"):  # a dropdown now
    return img * (0.5 if mode == "dark" else 1.0)


print(tone.describe(np.ones((2, 2)))["controls"][0]["kind"])  # dropdown
```

### Controls belong to the function

Controls are attached to the decorated function instead of a process-wide
registry keyed by `module.qualname`. Two scripts run in one interpreter with
same-named `__main__` filters, or filters made by a factory, no longer share
or replace each other's controls. Re-decorating a function (a notebook cell run
again) drops the controls it no longer declares. Nothing to change unless you relied on that sharing.

### Each pipeline owns its controls

Two pipelines built from the same filter no longer share control values: a
value set in one used to be the starting value of the other. A pipeline starts
from the declared default, and a direct call `amplify(img)` uses the declared
default too. To drive several filters of one pipeline with a single widget,
pass the same `Control` object to their decorators (see the
[controls guide](guide/controls.md)).

```python
import numpy as np
from interactive_pipe import interactive, interactive_pipeline


@interactive(gain=(1.0, [0.0, 3.0]))
def amplify(img, gain=1.0):
    return img * gain


@interactive_pipeline(gui=None)
def first(img):
    out = amplify(img)
    return out


@interactive_pipeline(gui=None)
def second(img):
    out = amplify(img)
    return out


first(np.ones((2, 2)), gain=3.0)
(out,) = second(np.ones((2, 2)))  # 1.0: the value set in `first` stays there
if out.max() != 1.0:
    raise RuntimeError(out.max())
```

### Snapshots and sweeps start from a fresh context

Each `snapshot` call and each `sweep` cell is rendered like a first run: the
`context` holds only what the pipeline was given at construction, and the live
pipeline's state is untouched afterwards. Before, a pipeline keeping state in
`context` (a simulation, an accumulator) continued from wherever the previous
call left it, so sweep cells depended on each other.

```python
import numpy as np
from interactive_pipe import context, interactive, interactive_pipeline


@interactive(gain=(1.0, [0.0, 3.0]))
def count(gain=1.0):
    context["n"] = context.get("n", 0) + 1
    return np.full((8, 8), context["n"] / 10.0)


@interactive_pipeline(gui=None)
def pipe():
    frame = count()
    return frame


first, second = pipe.snapshot(None, gain=1.0), pipe.snapshot(None, gain=2.0)
if not np.array_equal(first[:20, :20], second[:20, :20]):  # same picture: both are a first run
    raise RuntimeError("snapshots depend on each other")
```

## Display

### 2D arrays are gray on the matplotlib backend too

The matplotlib backend showed 2D arrays with matplotlib's default colormap
(viridis) and kept the colour limits of the first frame; Qt, Dear PyGui,
Gradio and snapshots showed gray. Every backend now shows gray. For a
false-colour view, ask for it:

```python
import numpy as np
from interactive_pipe import interactive, interactive_pipeline, layout


@interactive()
def heat(img):
    layout.style("heatmap", colormap="viridis", colorbar=True)  # was implicit on mpl only
    return img.mean(axis=-1)


@interactive_pipeline(gui=None)
def pipe(img):
    heatmap = heat(img)
    return heatmap


pipe.snapshot("/tmp/heat.png", np.random.rand(16, 16, 3))
```

### Integer, RGBA and single-channel images

`(H, W, 1)` is shown as `(H, W)`, RGBA on a checkerboard, `bool` as 0 / 1,
`uint8` divided by 255, `uint16` by 65535, on every backend (Qt raised on
`(H, W, 1)` and RGBA, and the GUI backends showed integer images white).
Other integer types (`int32`, `int64`) are taken as values like floats, so
0-255 data in `int64` is clipped: `snapshot`, `sweep` and
`interactive-pipe check` warn with the fix. Convert it:

```python
import numpy as np
from interactive_pipe import interactive


@interactive()
def counts(img):
    return (img * 255).astype(np.uint8)  # not .astype(int): uint8 is shown as 0-255
```

### Arrays that cannot be displayed raise `DisplayError`

Channel-first `(3, H, W)` arrays, batches, empty, complex and object arrays
crashed each GUI backend differently and were drawn as placeholders by 0.9's
snapshot. `snapshot` / `sweep` now raise `DisplayError` (a `ValueError`)
naming the output, the filter and the fix; a GUI window shows the message in
the cell and keeps running.

Before (now raises `DisplayError: output 'out' (returned by filter 'to_chw') cannot be displayed: channel-first array (3, 8, 8). Fix: move the channels last: np.moveaxis(img, 0, -1).`):

<!-- code: raises DisplayError -->
```python
import numpy as np
from interactive_pipe import interactive, interactive_pipeline


@interactive()
def to_chw(img):
    return np.moveaxis(img, -1, 0)


@interactive_pipeline(gui=None)
def pipe(img):
    out = to_chw(img)
    return out


pipe.snapshot(None, np.zeros((8, 8, 3)))
```

After: return channels last (`np.moveaxis(chw, 0, -1)`).

### `pyplot` figures are closed once displayed

A filter returning a figure made with `pyplot` sees it closed after it is
rasterised (no leak while a slider moves). Keep no reference to it between
runs, or build figures with `matplotlib.figure.Figure()`, which needs no
closing. Headless runs (`pipe(img)`, `my_pipeline.headless(img)`) close them
too: a returned figure can still be saved (`fig.savefig(...)`), but a later
`plt.show()` no longer shows it; a direct call of the filter
(`histogram(img)`) is plain Python and leaves it open.


```python
from matplotlib.figure import Figure
from interactive_pipe import interactive


@interactive()
def histogram(img):
    fig = Figure(figsize=(4, 3))
    fig.subplots().hist(img.ravel(), bins=32)
    return fig
```

### `layout.style` calls on one output add up

Two `layout.style` calls on the same output during one run used to keep only
the last one, so styling once and setting a readout title later dropped the
colormap / range. Calls now add up (a later call changes only the keys it
gives; `key=None` removes one); the first call of the next run starts from
nothing. Code relying on a second call clearing the first one's keys passes
them as `None`:

```python
import numpy as np
from interactive_pipe import interactive, interactive_pipeline, layout


@interactive()
def heat():
    layout.style("h", colormap="viridis", vmin=0, vmax=10)
    layout.style("h", title="readout")  # keeps the colormap and the range
    layout.style("h", vmax=None)  # removes vmax: back to the data max
    return np.linspace(0, 10, 64).reshape(8, 8)


@interactive_pipeline(gui=None)
def pipe():
    h = heat()
    return h


pipe()
assert pipe.styles["h"] == {"colormap": "viridis", "vmin": 0, "title": "readout"}
```

### Figures laid out with `tight_layout()` are laid out again in their cell

A figure on which the filter called `fig.tight_layout()` at its own
`figsize` kept those margins when drawn smaller in a cell, so its labels
could be cut. It is now laid out again at the cell size (its margins are
put back afterwards); `subplots_adjust` without a layout engine is still
kept as given. To keep exact margins, use a layout engine of your own
(`Figure(layout="constrained")`) or `subplots_adjust`:

```python
from matplotlib.figure import Figure
from interactive_pipe import interactive


@interactive()
def plot(img):
    fig = Figure(figsize=(6, 4))
    fig.subplots().plot(img.mean(axis=0))
    fig.tight_layout()  # fine: redone at the size of the cell
    return fig
```

## Errors and logs

- **A failing filter is reported once.** The engine no longer prints a
  `PIPELINE ERROR` banner before raising `FilterError`; an uncaught error
  prints it once (full traceback with `INTERACTIVE_PIPE_DEBUG=1`), a GUI window
  once per distinct error. Code parsing the console output for the banner of a
  caught error will not find it any more.
- **Out-of-range values are clamped with a warning** (`pipe(img, gain=99)`,
  tuning files, sessions): `Control 'gain': value 99.0 is outside its range
  [0.0, 2.0], clamped to 2.0`.
- **Reworded messages** (tests matching message text): a default outside its
  range now says `the default 5 is outside the range [0, 3]: choose a default
  between 0 and 3, or widen the range` (was `value_default 5 must be within
  value_range [0, 3]`); `snapshot()` / `sweep()` unknown names read like the
  pipeline call's (`got unexpected keyword argument(s) 'gian'. Available
  parameters: ...`); `layout.style(...)`, `context[...]`, `events[...]` and
  `audio.*` outside a filter name the call and show the fix.
- **`import interactive_pipe` no longer imports** `matplotlib.pyplot`, pandas,
  OpenCV or Pillow: they are imported when an image or a curve is saved,
  loaded, plotted or rendered. Import them yourself if your script used them
  without importing them.
