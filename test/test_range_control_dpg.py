"""RangeControl Dear PyGui widget (no viewport): one drawn two-handle slider producing (lo, hi)."""

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
    assert dpg.does_item_exist(widget.drawlist)
    assert (widget.lo, widget.hi) == pytest.approx((0.2, 0.8))
    int_widget = gui.window.widget_list["dpg_bins"]
    assert (int_widget.lo, int_widget.hi) == (2, 5)


def test_drag_produces_tuple_and_keeps_order():
    gui = build_gui()
    window = gui.window
    widget = window.widget_list["dpg_window"]
    widget._move("lo", 0.9)  # lo above hi pushes hi
    assert window.ctrl["dpg_window"].value == pytest.approx((0.9, 0.9))
    assert widget.hi == pytest.approx(0.9)
    widget._move("hi", 0.3)  # hi below lo pushes lo
    assert window.ctrl["dpg_window"].value == pytest.approx((0.3, 0.3))
    int_widget = window.widget_list["dpg_bins"]
    int_widget._move("hi", 7)
    assert window.ctrl["dpg_bins"].value == (2, 7)
    assert all(type(v) is int for v in window.ctrl["dpg_bins"].value)


def test_press_grabs_nearest_handle_and_snaps():
    gui = build_gui()
    gui.reset_parameters()  # the decorated control keeps state across tests
    window = gui.window
    widget = window.widget_list["dpg_window"]
    widget._press(widget._x_of(0.85))  # nearest to hi (0.8)
    assert widget._drag == "hi"
    widget._move("hi", widget._value_at(widget._x_of(1.0)))
    widget._release()
    assert widget._drag is None
    assert window.ctrl["dpg_window"].value == pytest.approx((0.2, 1.0))
    widget._press(widget._x_of(0.1))  # nearest to lo (0.2)
    assert widget._drag == "lo"
    widget._release()


def test_reset_restores_default():
    gui = build_gui()
    window = gui.window
    widget = window.widget_list["dpg_window"]
    widget._move("lo", 0.5)
    window.reset_sliders()
    assert widget.lo == pytest.approx(0.5)  # reset_sliders follows the control
    gui.reset_parameters()
    assert window.ctrl["dpg_window"].value == (0.2, 0.8)
    assert (widget.lo, widget.hi) == pytest.approx((0.2, 0.8))
