# Testing filters and pipelines

Decorated filters stay plain functions, and every pipeline can run without a
window, so ordinary `pytest` tests work on both.

## Call a filter directly

An `@interactive` filter called outside a pipeline run behaves like the
undecorated function, with the declared defaults (or the values you pass):

- `layout.style(...)`, `layout.grid(...)` and `audio` calls are validated, then
  do nothing;
- `events.get(name)` returns its default (no key is pressed);
- `context` is a scratch dict for the duration of the call: writes are
  discarded afterwards, and reading a key nobody wrote raises a `KeyError`
  saying the filter is called directly (use `context.get(key, default)` in the
  filter, or test it inside a pipeline).

```python
import numpy as np

from interactive_pipe import context, interactive, layout


@interactive(gain=(1.0, [0.0, 2.0]))
def compare(out, gt, gain=1.0):
    layout.style("error", title="error", colormap="magma")
    context["mse"] = float(np.mean((out - gt) ** 2))
    return np.abs(out - gt) * gain


def test_compare():
    error = compare(np.ones((4, 4)), np.zeros((4, 4)))
    assert error.max() == 1.0
    assert compare(np.ones(2), np.zeros(2), gain=0.5).max() == 0.5


test_compare()
```

Outside any filter (at module level) these calls still raise `RuntimeError`.

## Get the outputs of a GUI pipeline

`my_pipeline.headless(img, gain=2.0)` runs a pipeline decorated with any
`gui=` without opening a window and returns its outputs as a tuple, like a
`gui=None` pipeline (`(single,) = ...` for one output). It is a separate
`HeadlessPipeline` of the same function: its control values do not change the
window's. On a `HeadlessPipeline`, `.headless` is the pipeline itself.

```python
import numpy as np

from interactive_pipe import interactive, interactive_pipeline


@interactive(gain=(1.0, [0.0, 3.0]))
def amplify(img, gain=1.0):
    return img * gain


@interactive_pipeline(gui="qt")
def demo(img):
    amplified = amplify(img)
    return amplified


(out,) = demo.headless(np.ones(3), gain=2.0)
assert out.tolist() == [2.0, 2.0, 2.0]
```

## Read the titles and styles of the last run

A readout written in a title (`layout.style("overlay", title=f"IoU {iou:.2f}")`)
is not part of the outputs; `pipe.styles` gives the `layout.style` options of
each output after the last run (a copy), also through `.headless`:

```python
import numpy as np

from interactive_pipe import interactive, interactive_pipeline, layout


@interactive(gain=(1.0, [0.0, 3.0]))
def measured(img, gain=1.0):
    out = img * gain
    layout.style("out", title=f"mean {out.mean():.1f}")
    return out


@interactive_pipeline(gui="qt")
def readout(img):
    out = measured(img)
    return out


readout.headless(np.ones(3), gain=2.0)
assert readout.headless.styles["out"]["title"] == "mean 2.0"
```

A filter with a `PointControl` / `RegionControl` aimed (`on=`) at an output
that a small `gui=None` test pipeline does not produce only logs a warning
there (a GUI pipeline raises): the control keeps its value.

## Reproducible snapshots of stateful pipelines

`snapshot` and every `sweep` cell start like a first run: the `context` holds
only what was given from outside (`context=` at construction or in a call),
key-bound events are off and nothing comes from the cache; the live pipeline's
context is put back afterwards. A pipeline that needs warm-up runs (an
accumulator, a simulation) takes `runs=N`: the N-th run from that fresh start.

```python
import numpy as np

from interactive_pipe import context, interactive, interactive_pipeline


@interactive()
def accumulate():
    context["n"] = context.get("n", 0) + 1
    return np.full((8, 8), context["n"] / 10)


@interactive_pipeline(gui=None)
def counter():
    level = accumulate()
    return level


first = counter.snapshot(None)
counter()  # the live state moves on...
assert (counter.snapshot(None) == first).all()  # ...snapshots do not
warm = counter.snapshot(None, runs=5)  # the 5th run from a fresh context
```
