---
name: build-interactive-pipeline
description: Build or modify an interactive_pipe GUI pipeline — filter functions with @interactive controls, an @interactive_pipeline function, backend choice, and the context/layout proxies. Use when creating slider/GUI apps with interactive_pipe or debugging its decorators.
---

# Build an interactive_pipe pipeline

## Scaffold recipe

```python
from interactive_pipe import interactive, interactive_pipeline
import numpy as np


@interactive(gain=(1.0, [0.0, 3.0]), flip=(False,))
def amplify(img, gain=1.0, flip=False):
    out = img * gain
    return out[::-1] if flip else out


@interactive(blend_coeff=(0.5, [0.0, 1.0]))
def blend(img0, img1, blend_coeff=0.5):
    return (1 - blend_coeff) * img0 + blend_coeff * img1


@interactive_pipeline(gui="qt")
def my_pipeline(img):
    amplified = amplify(img)
    blended = blend(img, amplified)
    return amplified, blended


my_pipeline(np.random.rand(256, 512, 3))  # opens the GUI
```

Images are float numpy arrays in `[0, 1]`, shape `(H, W, 3)` or `(H, W)`.

## HARD RULE: the pipeline function body

The `@interactive_pipeline` function is never executed: its body is parsed statically to build the execution graph. Every top-level statement is checked, and anything outside this list raises `PipelineSyntaxError` (a `ValueError`) at decoration time, naming the file, line and the fix:

- a docstring, `pass`, `...`
- a filter call, assigned or not: `out = flt(img)`, `a, b = flt(img)`, `flt(img)`, `gen()` (no input)
- nested calls: `out = blur(amplify(img))` (the inner result is named `amplify(img)`)
- literal keyword arguments: `amplify(img, gain=2.5)` — sets that instance's value (and its control default); must be a parameter of the filter and a literal (number, string, bool, None, tuple, list, dict)
- dotted calls: `np.abs(img)`, `lib.blur(img)` (resolved in the function's real scope — pipelines and filters may live inside `main()`)
- one final `return`: names, `None`, tuples, (nested) lists, or calls: `return amplify(img)`

Rejected (each with a hint): `if`/`for`/`while`/`with`/`try`/`match`, arithmetic or any expression that is not a call (`b = a * 2`, `img[0]`, `x.attr`), `+=`, comprehensions, lambdas, statements after `return`, `*args`/`**kwargs` in calls, positional literals (`blur(img, 3)` → write `blur(img, radius=3)`), variables as keyword values (`amplify(img, gain=g)`), builtins (`print(img)`), unknown names (with a "did you mean"). Put all logic inside filters.

```python
# WRONG — PipelineSyntaxError             # RIGHT
@interactive_pipeline(gui="qt")           @interactive_pipeline(gui="qt")
def pipe(img):                            def pipe(img):
    if dark:                                  styled = apply_style(img)  # if lives inside apply_style
        img = darken(img)                     return scale(styled, factor=2.0)
    return img * 2
```

## Control declarations (in the `@interactive(...)` decorator)

| Widget | Declaration |
|---|---|
| Float slider | `gain=(1.0, [0.0, 3.0])` — optional 3rd element = label string |
| Int slider | `size=(5, [1, 15])` (int default + int bounds; optional `step`) |
| Checkbox | `flip=True` or `flip=(True,)` (in the decorator; a bare `True` in the signature gets no widget) |
| Dropdown | `mode=("dark", ["dark", "light"])` or just `mode=["dark", "light"]` |
| Key toggle | `flip=KeyboardControl(True, keydown="k")` — press k instead of a checkbox (no tuple shorthand for key bindings) |
| Explicit object | `gain=Control(1.0, [0.0, 3.0], name="gain", step=0.1, group="Panel A", tooltip="...")` |
| Keyboard-driven | `idx=KeyboardControl(0, [0, 2], keydown="pagedown", keyup="pageup", modulo=True)` |
| Text box | `txt=TextPrompt("hello")` |
| Animation timer | `t=TimeControl(update_interval_ms=50)` (Qt and dpg only; falls back to slider) |

Import `Control`, `KeyboardControl`, `TextPrompt`, `TimeControl`, `Panel` from `interactive_pipe`. Group controls with `group="name"` or a `Panel` instance (nestable, collapsible).

The decorated function's own default (`gain=1.0`) is overridden by the control's default. A kwarg with no declaration simply gets no widget. In the decorator, a bare number or string (`@interactive(gain=1.0)`) raises `ValueError`: a slider needs a range `(1.0, [0.0, 2.0])`, a dropdown a list of choices.

Two filters may both declare a `gain` control: in one pipeline they are shown as `amplify.gain` and `blend.gain` (explicit `name=...` collisions still raise). `pipe(img, gain=2.0)` sets `gain` in every filter having it; target one with `pipe(img, parameters={"blend": {"gain": 2.0}})`.

## Backends (`gui=` argument)

- `"qt"` — richest (needs `pip install "interactive-pipe[qt6]"`)
- `"dpg"` — Dear PyGui GPU-rendered window, same features as Qt minus audio (needs `pip install "interactive-pipe[dpg]"`)
- `"mpl"` — always available (matplotlib is a core dep)
- `"nb"` — Jupyter/Colab (needs `[notebook]` extra)
- `"gradio"` — web app (needs gradio)
- `"auto"` — best available
- `None` / `"headless"` — **no GUI, returns a `HeadlessPipeline`**: use this in tests and batch scripts. Call it like a function, override params by kwargs: `pipe(img, gain=2.0)` (an unknown keyword raises `TypeError`; out-of-range values are clamped with a warning). `pipe.save("out/res.png")` writes every output (images, curves, tables...) and returns the written paths. `pipe.export_tuning("t.yaml")` / `pipe.load_tuning("t.yaml")` persist parameters.

For one-off single-filter GUIs there is also `@interact(input_img, gain=(1.0, [0.0, 3.0]))` which launches immediately at decoration time.

## Sharing state and styling outputs: proxies

```python
from interactive_pipe import context, layout, audio, events


@interactive()
def my_filter(img):
    context["avg"] = float(img.mean())  # share data between filters
    layout.style("out", title="My image")  # "out" = variable name in the pipeline function
    layout.style("heat", colormap="viridis", vmin=0, vmax=1)  # 2D arrays as heatmaps
    layout.grid([["input", "out"]])  # arrange the display
    return img
```

**NEVER generate `global_params=` (or `context=`, `state=`, ...) in a filter signature** — this injection pattern was removed in 0.9.0 and raises `TypeError` at construction. Use the proxies above; seed initial values via `@interactive_pipeline(context={...})`.

## Common errors

| Symptom | Fix |
|---|---|
| `TypeError: ... removed in interactive_pipe 0.9.0` | Drop `global_params`/`state` kwarg; use the `context` proxy |
| `PipelineSyntaxError: pipeline 'p', file.py, line N: ...` | Pipeline body has logic/arithmetic/unsupported syntax — follow the `Hint:` line (usually: move it into a filter) |
| `PipelineSyntaxError: name 'x' is not defined ... did you mean` | Typo in a filter name, or the filter is not imported/defined before the pipeline |
| `TypeError: pipeline 'p' got unexpected keyword argument(s)` | Typo in `pipe(img, gian=...)` — the message lists the parameters |
| `ValueError: pipeline 'p' expects 1 input (img), got 0` | Pass every input of the pipeline function |
| `ValueError: @interactive(gain=1.0): a bare value cannot make a widget` | Give a range `gain=(1.0, [0.0, 2.0])`, or put the default in the signature |
| `Duplicate control name 'x'` | Two controls explicitly named `x` (`name=...`) in one pipeline: rename one |
| Warning `Control 'x': value ... is outside its range` | The value was clamped: widen the range or fix the value |
| Blank/no window in CI or headless env | Use `gui=None` (or mpl with `MPLBACKEND=Agg`, qt with `QT_QPA_PLATFORM=offscreen`) |
| Widget missing for a parameter | The kwarg wasn't declared in `@interactive(...)` (a bare default in the signature gets no widget) |
| `value_default ... must be within value_range` | Default outside `[min, max]` |

## References

- Docs: https://balthazarneveu.github.io/interactive_pipe/ (full text: `/llms-full.txt` on the same host)
- In-repo: `demo/` (17 feature demos), `samples/` (declaration styles), `test/` (headless usage patterns)
