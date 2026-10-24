"""RangeControl Dear PyGui widget (no viewport): two linked sliders producing (lo, hi)."""

import numpy as np
import pytest

dpg_gui = pytest.importorskip("interactive_pipe.graphical.dpg_gui")

from interactive_pipe import RangeControl, interactive  # noqa: E402
from interactive_pipe.graphical import dpg_backend, dpg_control  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

dpg = dpg_backend.dpg

INPUT_IMAGE = np.linspace(0.0, 1.0, 4 * 4, dtype=np.float64).reshape(4, 4)


@pytest.fixture(autouse=True)
def _fresh_dpg_context():
    yield
    dpg_backend.destroy_context()


@interactive(
    dpg_window=RangeControl((0.2, 0.8), [0.0, 1.0]),
    dpg_bins=RangeControl((2, 5), [0, 10]),
)
def dpg_range_clip(img, dpg_window=(0.2, 0.8), dpg_bins=(2, 5)):
    lo, hi = dpg_window
    return np.clip(img, lo, hi)


def dpg_range_pipeline(img):
    clipped = dpg_range_clip(img)
    return clipped


def build_gui():
    pipeline = HeadlessPipeline.from_function(dpg_range_pipeline, inputs=["img"])
    gui = dpg_gui.InteractivePipeDPG(pipeline=pipeline, name="range smoke")
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    return gui


def test_items_exist_with_default_values():
    gui = build_gui()
    widget = gui.window.widget_list["dpg_window"]
    assert isinstance(widget, dpg_control.RangeSliderControl)
    assert dpg.does_item_exist(widget.lo_widget) and dpg.does_item_exist(widget.hi_widget)
    assert dpg.get_value(widget.lo_widget) == pytest.approx(0.2)
    assert dpg.get_value(widget.hi_widget) == pytest.approx(0.8)
    int_widget = gui.window.widget_list["dpg_bins"]
    assert (dpg.get_value(int_widget.lo_widget), dpg.get_value(int_widget.hi_widget)) == (2, 5)


def test_callbacks_produce_tuple_and_keep_order():
    gui = build_gui()
    window = gui.window
    widget = window.widget_list["dpg_window"]
    widget._on_lo_change(None, 0.9, None)  # lo above hi pushes hi
    assert window.ctrl["dpg_window"].value == pytest.approx((0.9, 0.9))
    assert dpg.get_value(widget.hi_widget) == pytest.approx(0.9)
    widget._on_hi_change(None, 0.3, None)  # hi below lo pushes lo
    assert window.ctrl["dpg_window"].value == pytest.approx((0.3, 0.3))
    int_widget = window.widget_list["dpg_bins"]
    int_widget._on_hi_change(None, 7, None)
    assert window.ctrl["dpg_bins"].value == (2, 7)
    assert all(type(v) is int for v in window.ctrl["dpg_bins"].value)


def test_reset_restores_default():
    gui = build_gui()
    window = gui.window
    widget = window.widget_list["dpg_window"]
    widget._on_lo_change(None, 0.5, None)
    window.reset_sliders()
    assert dpg.get_value(widget.lo_widget) == pytest.approx(0.5)  # reset_sliders follows the control
    gui.reset_parameters()
    assert window.ctrl["dpg_window"].value == (0.2, 0.8)
    assert dpg.get_value(widget.lo_widget) == pytest.approx(0.2)
    assert dpg.get_value(widget.hi_widget) == pytest.approx(0.8)
