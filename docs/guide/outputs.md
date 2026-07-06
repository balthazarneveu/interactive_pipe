# Curves, tables & audio

Filters usually return image arrays, but they can also return **plots** (`Curve`), **tables** (`Table`) and drive **audio playback** — the GUI picks the right widget for each output. All backends display curves and tables; audio is Qt and Gradio ([backend matrix](../getting-started/backends.md)).

## Curve plots

Return a `Curve` from a filter to display a 2D plot instead of an image. The most compact form is a list of `[x, y, style, label]` entries (matplotlib-style format strings):

```python
from interactive_pipe import Curve, interactive
import numpy as np

@interactive(
    frequency=(2.0, [0.5, 10.0]),
    amplitude=(1.0, [0.1, 2.0]),
)
def generate_curve(frequency=2.0, amplitude=1.0) -> Curve:
    x = np.linspace(0.0, 4.0 * np.pi, 200)
    y_main = amplitude * np.sin(frequency * x)
    y_ref = amplitude * np.cos(frequency * x)
    return Curve(
        [
            [x, y_main, "b-", f"sin({frequency:.2f}x)"],
            [x, y_ref, "r--", f"cos({frequency:.2f}x)"],
        ],
        xlabel="x [rad]",
        ylabel="y",
        ylim=[-2.5, 2.5],
        grid=True,
        title=f"Oscillations (A={amplitude:.2f})",
    )
```

- `Curve(...)` accepts axis labels, `title`, `grid`, and `xlim`/`ylim` (fixing the limits avoids the axes jumping around while you move sliders).
- Each entry can also be a `SingleCurve(x, y, style=..., label=..., linewidth=..., alpha=...)` for finer control, a bare numpy array (plotted against its indices), or a dict of `SingleCurve` kwargs.
- Curves update live as sliders move, like any other output, and mix freely with images in the same pipeline — arrange them with [`layout.grid`](context-layout.md#layout-arrange-and-style-the-outputs).

Full example: [demo/independent_curve_image_demo.py](https://github.com/balthazarneveu/interactive_pipe/blob/master/demo/independent_curve_image_demo.py) (a curve and an image side by side, sharing sliders).

## Tables

Return a `Table` to display tabular data — handy for live statistics next to the image being processed:

```python
from interactive_pipe import Table, interactive

@interactive()
def compute_statistics(img) -> Table:
    channels = ["Red", "Green", "Blue"]
    stats = {
        "Channel": channels,
        "Mean": [img[:, :, i].mean() for i in range(3)],
        "Std": [img[:, :, i].std() for i in range(3)],
    }
    return Table(stats, title="Image statistics", precision=4)
```

`Table` accepts several input shapes:

- a dict of columns: `{"Channel": [...], "Mean": [...]}` (as above)
- a 2D numpy array plus `columns=["X", "Y", ...]`
- a numpy array with `columns=None` for a headerless raw matrix
- a list of row dicts: `[{"x": 1, "y": 2}, ...]`
- a pandas `DataFrame` (when pandas is installed; pandas is optional)

`precision` controls float formatting. Tables render on all four backends.

Full example: [demo/table_demo.py](https://github.com/balthazarneveu/interactive_pipe/blob/master/demo/table_demo.py) (statistics, coordinate grids, DataFrames side by side).

## Audio

Audio is not returned from filters — it is driven by the `audio` proxy as a side effect, typically reacting to a control:

```python
from interactive_pipe import audio, interactive

@interactive(song=(["silence", "elephant", "snail"]))
def choose_song(img, song="silence"):
    if song == "silence":
        audio.stop()
    else:
        audio.set(f"tracks/{song}.mp4")
        audio.play()
    return img
```

- `audio.set(path)` registers the file, `audio.play()` / `audio.pause()` / `audio.stop()` control playback.
- Supported on the **Qt** backend (this is how the [Raspberry Pi jukebox](https://github.com/balthazarneveu/interactive_pipe/blob/master/demo/jukebox_demo.py) works) and on **Gradio**.
- On Gradio you can additionally return 1D numpy arrays from filters to display audio players.
- Outside a GUI (headless), the audio calls are silent no-ops, so the same filter stays batch-safe.

## API

Constructor details: [Data objects](../api/data-objects.md) (`Image`, `Curve`, `SingleCurve`, `Table`) and [Context & layout](../api/context.md) (the `audio` proxy).
