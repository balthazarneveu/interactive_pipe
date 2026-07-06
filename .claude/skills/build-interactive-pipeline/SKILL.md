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

The `@interactive_pipeline` function is parsed by an AST analyzer to build the execution graph. Its body may contain **only filter-function calls, assignments and a return** — NO if/else/for/while, NO arithmetic, NO numpy calls. Violating this breaks graph construction. Put all logic inside filters.

```python
# WRONG — breaks the AST parser          # RIGHT
@interactive_pipeline(gui="qt")           @interactive_pipeline(gui="qt")
def pipe(img):                            def pipe(img):
    if dark:                                  styled = apply_style(img)  # if lives inside apply_style
        img = darken(img)                     return styled
    return img * 2
```

## Control declarations (in the `@interactive(...)` decorator)

| Widget | Declaration |
|---|---|
| Float slider | `gain=(1.0, [0.0, 3.0])` — optional 3rd element = label string |
| Int slider | `size=(5, [1, 15])` (int default + int bounds; optional `step`) |
| Checkbox | `flip=(True,)` — note the trailing comma |
| Dropdown | `mode=("dark", ["dark", "light"])` or just `mode=["dark", "light"]` |
| Key toggle | `flip=KeyboardControl(True, keydown="k")` — press k instead of a checkbox (no tuple shorthand for key bindings) |
| Explicit object | `gain=Control(1.0, [0.0, 3.0], name="gain", step=0.1, group="Panel A", tooltip="...")` |
| Keyboard-driven | `idx=KeyboardControl(0, [0, 2], keydown="pagedown", keyup="pageup", modulo=True)` |
| Text box | `txt=TextPrompt("hello")` |
| Animation timer | `t=TimeControl(update_interval_ms=50)` (Qt only; falls back to slider) |

Import `Control`, `KeyboardControl`, `TextPrompt`, `TimeControl`, `Panel` from `interactive_pipe`. Group controls with `group="name"` or a `Panel` instance (nestable, collapsible).

The decorated function's own default (`gain=1.0`) is overridden by the control's default. A kwarg with no declaration simply gets no widget.

## Backends (`gui=` argument)

- `"qt"` — richest (needs `pip install "interactive-pipe[qt6]"`)
- `"mpl"` — always available (matplotlib is a core dep)
- `"nb"` — Jupyter/Colab (needs `[notebook]` extra)
- `"gradio"` — web app (needs gradio)
- `"auto"` — best available
- `None` / `"headless"` — **no GUI, returns a `HeadlessPipeline`**: use this in tests and batch scripts. Call it like a function, override params by kwargs: `pipe(img, gain=2.0)`. `pipe.export_tuning("t.yaml")` / `pipe.load_tuning()` persist parameters.

For one-off single-filter GUIs there is also `@interact(input_img, gain=(1.0, [0.0, 3.0]))` which launches immediately at decoration time.

## Sharing state and styling outputs: proxies

```python
from interactive_pipe import context, layout, audio, events

@interactive()
def my_filter(img):
    context["avg"] = float(img.mean())     # share data between filters
    layout.style("out", title="My image")  # "out" = variable name in the pipeline function
    layout.grid([["input", "out"]])        # arrange the display
    return img
```

**NEVER generate `global_params=` (or `context=`, `state=`, ...) in a filter signature** — this injection pattern was removed in 0.9.0 and raises `TypeError` at construction. Use the proxies above; seed initial values via `@interactive_pipeline(context={...})`.

## Common errors

| Symptom | Fix |
|---|---|
| `TypeError: ... removed in interactive_pipe 0.9.0` | Drop `global_params`/`state` kwarg; use the `context` proxy |
| Graph/AST error at decoration time | Pipeline body has logic/arithmetic — move it into a filter |
| Blank/no window in CI or headless env | Use `gui=None` (or mpl with `MPLBACKEND=Agg`, qt with `QT_QPA_PLATFORM=offscreen`) |
| Widget missing for a parameter | The kwarg wasn't declared in `@interactive(...)` |
| `value_default ... must be within value_range` | Default outside `[min, max]` |

## References

- Docs: https://balthazarneveu.github.io/interactive_pipe/ (full text: `/llms-full.txt` on the same host)
- In-repo: `demo/` (17 feature demos), `samples/` (declaration styles), `test/` (headless usage patterns)
