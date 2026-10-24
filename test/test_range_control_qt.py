"""RangeControl Qt widget (offscreen): two linked sliders producing (lo, hi)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")

from interactive_pipe import RangeControl, interactive  # noqa: E402
from interactive_pipe.graphical.qt_control import ControlFactory, RangeSliderControl  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

INPUT_IMAGE = np.linspace(0.0, 1.0, 4 * 4, dtype=np.float64).reshape(4, 4)


@interactive(
    qt_window=RangeControl((0.2, 0.8), [0.0, 1.0]),
    qt_bins=RangeControl((2, 5), [0, 10]),
)
def qt_range_clip(img, qt_window=(0.2, 0.8), qt_bins=(2, 5)):
    lo, hi = qt_window
    return np.clip(img, lo, hi)


def qt_range_pipeline(img):
    clipped = qt_range_clip(img)
    return clipped


def build_gui():
    pipeline = HeadlessPipeline.from_function(qt_range_pipeline, inputs=["img"])
    gui = qt_gui.InteractivePipeQT(pipeline=pipeline, name="range smoke")
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    return gui


def test_factory_picks_range_slider():
    gui = build_gui()
    widget = gui.window.widget_list["qt_window"]
    assert isinstance(widget, RangeSliderControl)
    assert widget.lo_slider.value() == 20 and widget.hi_slider.value() == 80
    int_widget = gui.window.widget_list["qt_bins"]
    assert (int_widget.lo_slider.maximum(), int_widget.lo_slider.value(), int_widget.hi_slider.value()) == (10, 2, 5)


def test_moving_lo_above_hi_pushes_hi_and_back():
    gui = build_gui()
    window = gui.window
    widget = window.widget_list["qt_window"]
    widget.lo_slider.setValue(90)
    assert widget.hi_slider.value() == 90
    assert window.ctrl["qt_window"].value == pytest.approx((0.9, 0.9))
    widget.hi_slider.setValue(30)
    assert widget.lo_slider.value() == 30
    assert window.ctrl["qt_window"].value == pytest.approx((0.3, 0.3))
    qt_gui.QApplication.processEvents()
    assert gui.pipeline.parameters["qt_range_clip"]["qt_window"] == pytest.approx((0.3, 0.3))


def test_update_func_receives_tuple():
    received = []
    ctrl = RangeControl((1, 4), [0, 8], name="standalone")
    widget = ControlFactory.create_control(ctrl, lambda name, value: received.append((name, value)))
    widget.create()
    widget.hi_slider.setValue(6)
    widget.lo_slider.setValue(3)
    assert received == [("standalone", (1, 6)), ("standalone", (3, 6))]
    assert all(type(v) is int for v in received[-1][1])


def test_reset_restores_default():
    gui = build_gui()
    window = gui.window
    widget = window.widget_list["qt_window"]
    widget.lo_slider.setValue(50)
    widget.hi_slider.setValue(60)
    assert window.ctrl["qt_window"].value == pytest.approx((0.5, 0.6))
    gui.reset_parameters()
    assert window.ctrl["qt_window"].value == (0.2, 0.8)
    assert (widget.lo_slider.value(), widget.hi_slider.value()) == (20, 80)
