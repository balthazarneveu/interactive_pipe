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
| Audio support | ✅ | ➖ | ➖ | ➖ | ✅ |
| Image buttons | ✅ | ✅ | ➖ | ➖ | ➖ |
| Circular slider | ✅ | ✅ (knob) | ➖ | ➖ | ➖ |
| Collapsible panels | ✅ | ✅ | ➖ | ➖ | ✅ |
| Animations | ✅ | ✅ | ➖ | ➖ | ➖ |
| Panels with sliders | ✅ | ✅ | ➖ | ➖ | ✅ |
| Detached panels | ✅ | ✅ | ➖ | ➖ | ➖ |
| Tables | ✅ | ✅ | ✅ | ✅ | ✅ |

Controls degrade gracefully: for example a [`KeyboardControl`](../guide/keyboard.md) maps back to a regular slider on the gradio and notebook backends, and a `CircularControl` falls back to a straight slider outside Qt and Dear PyGui.

## Dear PyGui

`gui="dpg"` renders the window with [Dear PyGui](https://github.com/hoffstadt/DearPyGui) (`pip install "interactive-pipe[dpg]"`), an immediate-mode GPU toolkit that stays responsive with large images and fast refresh rates. It supports the same declarative features as Qt — panels at any position, collapsible and detached panels, keyboard shortcuts, `TimeControl` animations, image buttons and knobs for `CircularControl` — with native, zoomable plots for curve outputs and native tables. Images are scaled uniformly to fill the window (resize it to taste, or pass `size=(w, h)` / `"fullscreen"` / `"maximized"`). Audio playback is not available on this backend.

## Headless

`gui=None` (or `"headless"`) skips the GUI entirely and returns a `HeadlessPipeline`: the same pipeline code serves interactive tuning and batch processing, and it is what you want in unit tests. See the [Quickstart](quickstart.md#headless-mode-same-code-no-gui).
