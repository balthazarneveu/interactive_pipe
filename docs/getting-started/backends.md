# Backends

Select the backend with the `gui=` argument of `@interactive_pipeline` (or `@interact`): a string, a `Backend` enum value, or `None` for headless mode.

```python
@interactive_pipeline(gui="qt")      # PyQt / PySide window
@interactive_pipeline(gui="dpg")     # Dear PyGui window (GPU rendered)
@interactive_pipeline(gui="mpl")     # matplotlib figure
@interactive_pipeline(gui="nb")      # Jupyter notebook widgets (works on Colab)
@interactive_pipeline(gui="gradio")  # web app (add share_gradio_app=True to share it)
@interactive_pipeline(gui="auto")    # best available backend
@interactive_pipeline(gui=None)      # headless: returns a HeadlessPipeline
```

## Feature matrix

| ⭐ | *PyQt / PySide* | *Dear PyGui* | *Matplotlib* | *Jupyter notebooks incl. Google Colab* | *Gradio* |
|:-----:|:-----:|:-----:|:------:|:----:|:----:|
| Backend name | `qt` | `dpg` | `mpl` | `nb` | `gradio` |
| Preview | ![qt backend](../images/qt_backend.jpg) | ➖ | ![mpl backend](../images/mpl_backend.jpg) | ![nb backend](../images/notebook_backend.jpg) | ![gradio backend](../images/gradio_backend.jpg) |
| Plot curves | ✅ | ✅ (zoom & pan) | ✅ | ✅ | ✅ |
| Change layout | ✅ | ✅ | ✅ | ✅ | ➖ |
| Keyboard shortcuts / fullscreen | ✅ | ✅ | ✅ | ➖ | ➖ |
| Menu bar | ✅ | ✅ | ➖ | ➖ | ➖ |
| Audio support | ✅ | ➖ | ➖ | ➖ | ✅ |
| Image buttons | ✅ | ✅ | ➖ | ➖ | ➖ |
| Circular slider | ✅ | ✅ (knob) | ➖ | ➖ | ➖ |
| Collapsible panels | ✅ | ✅ | ➖ | ➖ | ✅ |
| Animations | ✅ | ✅ | ➖ | ➖ | ➖ |
| Panels with sliders | ✅ | ✅ | ➖ | ➖ | ✅ |
| Detached panels | ✅ | ✅ | ➖ | ➖ | ➖ |
| Tables | ✅ | ✅ | ✅ | ✅ | ✅ |
| Image viewer (fit / zoom / pan / pixel readout) | ✅ | ➖ fit only | ➖ | ➖ | ➖ |
| Status line (timings, errors) | ✅ | ✅ | ➖ | ➖ | ➖ |

Controls degrade gracefully: for example a [`KeyboardControl`](../guide/keyboard.md) maps back to a regular slider on the gradio and notebook backends, and a `CircularControl` falls back to a straight slider outside Qt and Dear PyGui.

## Dear PyGui

`gui="dpg"` renders the window with [Dear PyGui](https://github.com/hoffstadt/DearPyGui) (`pip install "interactive-pipe[dpg]"`), an immediate-mode GPU toolkit that stays responsive with large images and fast refresh rates. It supports the same declarative features as Qt — panels at any position, collapsible and detached panels, keyboard shortcuts, `TimeControl` animations, image buttons and knobs for `CircularControl` — with native, zoomable plots for curve outputs and native tables. Images are scaled uniformly to fill the window (resize it to taste, or pass `size=(w, h)` / `"fullscreen"` / `"maximized"`). Audio playback is not available on this backend.

## Headless

`gui=None` (or `"headless"`) skips the GUI entirely and returns a `HeadlessPipeline`: the same pipeline code serves interactive tuning and batch processing, and it is what you want in unit tests. See the [Quickstart](quickstart.md#headless-mode-same-code-no-gui).

## Choosing the backend from the command line or the environment

Switch backend or window size without editing your script.

### Command line: `interactive_pipe.cli`

`parse_gui_args()` adds `--gui {auto,qt,dpg,mpl,nb,gradio,headless}`, `--fullscreen`, `--maximized`, `--size WxH` and `--name` to an `argparse` parser and returns the parsed arguments together with the keyword arguments for `interactive_pipeline`. Only the options actually given end up in those kwargs, so with no flags you get `interactive_pipeline()` with all its defaults.

```python
from interactive_pipe import interactive_pipeline
from interactive_pipe.cli import parse_gui_args

args, gui_kwargs = parse_gui_args()
demo = interactive_pipeline(**gui_kwargs)(my_pipeline)  # gui="auto" unless --gui given
demo(img)
```

```bash
python my_script.py --gui dpg --size 1280x800
python my_script.py --fullscreen --name "Exposure tuning"
python my_script.py --gui headless     # gui=None: returns a HeadlessPipeline
```

To mix in your own options, pass your parser (`parse_gui_args(parser=my_parser)`), or call `add_gui_arguments(my_parser, defaults={"gui": "qt"})` then `gui_kwargs_from_args(my_parser.parse_args())`. `--fullscreen`, `--maximized` and `--size` are mutually exclusive; an invalid `--size` exits with a usage error.

### Environment variables

| Variable | Values | Effect |
|---|---|---|
| `INTERACTIVE_PIPE_GUI` | `auto`, `qt`, `dpg`, `mpl`, `nb`, `gradio`, `headless` / `none` | Replaces `gui` when the decorator uses `gui="auto"` (the default). `headless`/`none` returns a `HeadlessPipeline`. |
| `INTERACTIVE_PIPE_SIZE` | `fullscreen`, `maximized`, `WxH` (e.g. `1280x800`) | Window size when the decorator was not given a `size`. |

```bash
INTERACTIVE_PIPE_GUI=mpl INTERACTIVE_PIPE_SIZE=maximized python my_script.py
```

The variables are read when `interactive_pipeline` decorates the function. An invalid value raises `ValueError`. `INTERACTIVE_PIPE_GUI` also applies to `@interact`, except `headless`, which `@interact` ignores. `INTERACTIVE_PIPE_SIZE` is not applied to `@interact`. Not every backend accepts every size: the notebook backend only takes `(w, h)`, and Matplotlib has no `maximized`.

### Precedence

1. Command-line helper values: they are passed to the decorator as explicit arguments.
2. Explicit decorator arguments: any `gui` other than `"auto"` (including `gui=None`), and any `size`.
3. Environment variables.
4. Defaults: automatic backend selection, backend-specific window size.
