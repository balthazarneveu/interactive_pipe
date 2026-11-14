"""The layout.style display options go through one shared conversion
(graphical.display.prepare_display) used by the GUI backends, the Gradio
refresh path and the headless snapshot: a heatmap coloured in the GUI is
coloured in the snapshot too."""

import os

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import matplotlib  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402

from interactive_pipe import interactive, layout  # noqa: E402
from interactive_pipe.graphical.display import prepare_display  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402


@interactive()
def ramp_heatmap(img):
    layout.style("heat", title="Heat", colormap="viridis")
    h, w = img.shape[:2]
    return np.tile(np.linspace(-3.0, 7.0, w), (h, 1))


def heatmap_pipeline(img):
    heat = ramp_heatmap(img)
    return heat


def _chroma(rgb: np.ndarray) -> float:
    """Largest channel spread over the image: 0 for a gray image."""
    rgb = rgb[..., :3].astype(np.float64)
    return float((rgb.max(axis=-1) - rgb.min(axis=-1)).max())


def test_snapshot_of_a_styled_2d_array_is_not_gray():
    pipe = HeadlessPipeline.from_function(heatmap_pipeline)
    rendered = pipe.snapshot(None, np.zeros((32, 48, 3)))
    assert isinstance(rendered, np.ndarray)
    assert _chroma(rendered) > 100  # viridis: purple to yellow, on a 0-255 scale


def test_snapshot_colors_match_the_gui_conversion():
    """The snapshot cell content is exactly what the GUI windows get."""
    from interactive_pipe.headless.snapshot import result_grid

    pipe = HeadlessPipeline.from_function(heatmap_pipeline)
    out = pipe(np.zeros((8, 10, 3)))
    cell = result_grid(pipe, out)[0][0]
    expected = prepare_display(out[0], {"colormap": "viridis"})
    np.testing.assert_allclose(cell.content, expected)
    np.testing.assert_allclose(cell.content[0, 0], matplotlib.colormaps["viridis"](0.0)[:3])
    assert cell.title == "Heat"


def test_the_pipeline_result_stays_the_raw_map():
    pipe = HeadlessPipeline.from_function(heatmap_pipeline)
    out = pipe(np.zeros((8, 10, 3)))
    pipe.snapshot(None)
    assert out[0].shape == (8, 10)
    assert out[0][0, 0] == -3.0


def test_gradio_refresh_applies_the_colormap(monkeypatch):
    gr = pytest.importorskip("gradio")
    from interactive_pipe.graphical.gradio_gui import InteractivePipeGradio

    monkeypatch.setattr(gr.blocks.Blocks, "launch", lambda self, *a, **k: None, raising=True)
    pipe = HeadlessPipeline.from_function(heatmap_pipeline)
    gui = InteractivePipeGradio(pipeline=pipe, name="gradio heatmap")
    gui(np.zeros((8, 10, 3)))
    window = gui.window
    converted = window.run_fn(*window.default_values)
    assert isinstance(converted, np.ndarray)
    assert converted.shape == (8, 10, 3)  # RGB, not the raw 2D map
    assert _chroma(converted) > 100
