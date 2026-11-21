"""Regression tests for defects found by the November 2026 code audit (Qt window, offscreen)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")

from interactive_pipe import interactive  # noqa: E402
from interactive_pipe.headless.control import CircularControl, Control  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

INPUT_IMAGE = np.linspace(0.0, 1.0, 16).reshape(4, 4)


@interactive(show=Control(False))
def optional_output(img, show=False):
    return img if show else None


def optional_pipeline(img):
    maybe = optional_output(img)
    return img, maybe


@interactive(fine=(0.5, [0.0, 1.0]), free=Control(0.5), coarse=Control(0, [0, 6], step=4))
def precise(img, fine=0.5, free=0.5, coarse=0):
    return img * fine + free + coarse


def precise_pipeline(img):
    out = precise(img)
    return out


@interactive(flat=Control(0.5, [0.5, 0.5], step=0.1), turn=CircularControl(0.0, [0.0, 0.0], step=0.1))
def zero_range(img, flat=0.5, turn=0.0):
    return img * flat + turn


def zero_range_pipeline(img):
    out = zero_range(img)
    return out


def build_gui(pipeline_function):
    pipeline = HeadlessPipeline.from_function(pipeline_function, inputs=["img"])
    gui = qt_gui.InteractivePipeQT(pipeline=pipeline, name="audit")
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    return gui


def test_output_going_from_none_to_an_array_gets_its_cell():
    window = build_gui(optional_pipeline).window
    window.refresh()
    assert window.image_canvas[0][1] is None
    window.update_parameter("show", True)
    window.refresh()  # raised AttributeError: 'NoneType' object has no attribute 'get'
    assert window.image_canvas[0][1] is not None


def test_reset_keeps_the_exact_float_values():
    gui = build_gui(precise_pipeline)
    window = gui.window
    window.refresh()
    gui.pipeline.parameters = {"precise": {"fine": 0.98765, "free": 1e-5}}
    window.reset_sliders()  # the widgets (1000 positions, 4 decimals) must not write back
    assert gui.pipeline.parameters["precise"]["fine"] == 0.98765
    assert gui.pipeline.parameters["precise"]["free"] == 1e-5


def test_int_slider_stays_in_range_when_the_range_is_not_a_multiple_of_the_step():
    window = build_gui(precise_pipeline).window
    window.refresh()
    window.widget_list["coarse"].control_widget.setValue(6)
    assert window.ctrl["coarse"].value == 4


def test_zero_range_controls_build():
    window = build_gui(zero_range_pipeline).window
    window.refresh()
    assert window.ctrl["flat"].value == 0.5


def test_run_shows_a_window_closed_before(monkeypatch):
    gui = build_gui(optional_pipeline)
    monkeypatch.setattr(gui.app, "exec", lambda: 0)
    gui.window.close()
    assert not gui.window.isVisible()
    gui.run()
    assert gui.window.isVisible()
    gui.window.close()
