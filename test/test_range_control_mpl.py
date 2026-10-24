"""RangeControl matplotlib widget (Agg backend): native RangeSlider."""

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

mpl_gui = pytest.importorskip("interactive_pipe.graphical.mpl_gui")

from matplotlib.widgets import RangeSlider  # noqa: E402

from interactive_pipe import RangeControl, interactive  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

INPUT_IMAGE = np.linspace(0.0, 1.0, 4 * 4, dtype=np.float64).reshape(4, 4)


@interactive(
    mpl_window=RangeControl((0.2, 0.8), [0.0, 1.0]),
    mpl_bins=RangeControl((2, 5), [0, 10]),
)
def mpl_range_clip(img, mpl_window=(0.2, 0.8), mpl_bins=(2, 5)):
    lo, hi = mpl_window
    return np.clip(img, lo, hi)


def mpl_range_pipeline(img):
    clipped = mpl_range_clip(img)
    return clipped


def test_range_slider_created_and_drives_control():
    pipeline = HeadlessPipeline.from_function(mpl_range_pipeline, inputs=["img"])
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipeline, name="mpl range")
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    gui.window.refresh()
    slider = gui.window.sliders_list["mpl_window"]
    assert isinstance(slider, RangeSlider)
    assert tuple(slider.val) == pytest.approx((0.2, 0.8))
    slider.set_val((0.3, 0.6))
    assert gui.window.ctrl["mpl_window"].value == pytest.approx((0.3, 0.6))
    assert gui.pipeline.parameters["mpl_range_clip"]["mpl_window"] == pytest.approx((0.3, 0.6))
    int_slider = gui.window.sliders_list["mpl_bins"]
    int_slider.set_val((1, 7))
    assert gui.window.ctrl["mpl_bins"].value == (1, 7)
    assert all(type(v) is int for v in gui.window.ctrl["mpl_bins"].value)
    gui.reset_parameters()
    assert gui.window.ctrl["mpl_window"].value == (0.2, 0.8)
    assert tuple(gui.window.sliders_list["mpl_window"].val) == pytest.approx((0.2, 0.8))
    gui.close()
