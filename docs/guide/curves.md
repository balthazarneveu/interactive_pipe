# Curve plots

Return a `Curve` from a filter to display a 2D plot instead of an image. Curves update live as sliders move, like any other output, and mix freely with images in the same pipeline. All backends display them ([backend matrix](../getting-started/backends.md)).

## Returning a curve from a filter

The most compact form is a list of `[x, y, style, label]` entries (matplotlib-style format strings):

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

- `Curve(...)` accepts axis labels, `title`, `grid`, and `xlim`/`ylim` — fixing the limits avoids the axes jumping around while you move sliders.
- Each entry can also be a `SingleCurve(x, y, style=..., label=..., linewidth=..., alpha=...)` for finer control, a bare numpy array (plotted against its indices), or a dict of `SingleCurve` kwargs.
- Arrange curves next to images with [`layout.grid`](layout.md).

Full example: [demo/independent_curve_image_demo.py](https://github.com/balthazarneveu/interactive_pipe/blob/master/demo/independent_curve_image_demo.py) (a curve and an image side by side, sharing sliders).

## Standalone mode: plot without any pipeline

`Curve` is a plain data object — you can use it outside interactive_pipe entirely, as a thin matplotlib wrapper:

```python
from interactive_pipe import Curve, SingleCurve
import numpy as np

x = np.linspace(0, 1, 100)
curve = Curve([[x, x**2, "g-", "parabola"]], grid=True, xlabel="x")
curve.show()                    # opens a matplotlib figure
curve.show(figsize=(8, 4))

SingleCurve(x, np.sin(x)).show(title="standalone single curve")
```

`SingleCurve` also saves/loads to disk: `.save("signal.csv")` (x,y columns) or `.pkl`, and back with `SingleCurve.from_file("signal.csv")` — handy for comparing a live pipeline against recorded reference data.

## API

Constructor details: [`Curve` / `SingleCurve`](../api/data-objects.md).
