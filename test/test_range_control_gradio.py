"""RangeControl Gradio fallback: a 'lo, hi' text box (no server launch)."""

import os

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

gr = pytest.importorskip("gradio")

from interactive_pipe import RangeControl, interactive  # noqa: E402
from interactive_pipe.graphical.gradio_gui import InteractivePipeGradio  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

INPUT_IMAGE = np.linspace(0.0, 1.0, 4 * 4, dtype=np.float64).reshape(4, 4)


@pytest.fixture(autouse=True)
def no_launch(monkeypatch):
    monkeypatch.setattr(gr.Blocks, "launch", lambda self, *args, **kwargs: None)


@interactive(gr_window=RangeControl((0.2, 0.8), [0.0, 1.0]))
def gr_range_clip(img, gr_window=(0.2, 0.8)):
    lo, hi = gr_window
    return np.clip(img, lo, hi)


def gr_range_pipeline(img):
    clipped = gr_range_clip(img)
    return clipped


def test_text_fallback_feeds_a_tuple():
    pipeline = HeadlessPipeline.from_function(gr_range_pipeline, inputs=["img"])
    gui = InteractivePipeGradio(pipeline=pipeline, name="gradio range")
    gui(INPUT_IMAGE.copy())
    window = gui.window
    (widget,) = window.widget_list
    assert isinstance(widget, gr.Textbox)
    assert widget.value == "0.2, 0.8"
    window.run_fn("0.6, 0.3")
    assert gui.pipeline.parameters["gr_range_clip"]["gr_window"] == pytest.approx((0.3, 0.6))
    window.run_fn(*window.default_values)  # initial load passes the tuple itself
    assert gui.pipeline.parameters["gr_range_clip"]["gr_window"] == (0.2, 0.8)
