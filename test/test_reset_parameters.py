"""Regression tests: pressing ``r`` must reset *every* control, not just the first.

``HeadlessPipeline.update_parameters_from_controls`` used to assign
``self.parameters`` inside its per-control loop. The setter also writes the
values back into every control, so the first iteration pushed the (stale) filter
values over all the control values that ``reset_parameters`` had just set to
their defaults. Only the first control survived the reset.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from interactive_pipe import interactive  # noqa: E402
from interactive_pipe.headless.control import Control  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

INPUT_IMAGE = np.linspace(0.0, 1.0, 4 * 4, dtype=np.float64).reshape(4, 4)

DEFAULTS = {
    "first": {"gain": 0.5, "steps": 2},
    "second": {"inverted": False, "mode": "mean"},
}
CHANGED = {
    "first": {"gain": 1.0, "steps": 4},
    "second": {"inverted": True, "mode": "max"},
}


@interactive(gain=(0.5, [0.0, 1.0]), steps=(2, [0, 4]))
def first(img, gain=0.5, steps=2):
    return img * gain + steps


@interactive(inverted=Control(False), mode=("mean", ["mean", "max"]))
def second(img, inverted=False, mode="mean"):
    return 1.0 - img if inverted else img


def reset_pipeline(img):
    stage_1 = first(img)
    stage_2 = second(stage_1)
    return stage_2


def build_pipeline():
    pipeline = HeadlessPipeline.from_function(reset_pipeline, inputs=["img"])
    pipeline.inputs = [INPUT_IMAGE.copy()]
    return pipeline


def controls_by_parameter(pipeline):
    return {(ctrl.filter_to_connect.name, ctrl.parameter_name_to_connect): ctrl for ctrl in pipeline.controls}


def assert_everything_is_default(pipeline):
    assert pipeline.parameters == DEFAULTS
    for (filter_name, parameter), ctrl in controls_by_parameter(pipeline).items():
        assert ctrl.value == DEFAULTS[filter_name][parameter], f"{filter_name}.{parameter} control not reset"


def test_update_parameters_from_controls_applies_every_control():
    pipeline = build_pipeline()
    controls = controls_by_parameter(pipeline)
    # Control values changed without going through the filter (what reset_parameters does).
    for (filter_name, parameter), ctrl in controls.items():
        ctrl.value = CHANGED[filter_name][parameter]
    pipeline.run()
    assert pipeline.parameters == CHANGED
    for (filter_name, parameter), ctrl in controls.items():
        assert ctrl.value == CHANGED[filter_name][parameter], f"{filter_name}.{parameter} clobbered by a stale value"


def test_qt_reset_parameters_resets_every_control():
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    pipeline = build_pipeline()
    gui = qt_gui.InteractivePipeQT(pipeline=pipeline, name="reset")
    gui.window.refresh()
    window = gui.window
    window.update_parameter("gain", 1.0)
    window.update_parameter("steps", 4)
    window.update_parameter("inverted", True)
    window.update_parameter("mode", "max")
    assert pipeline.parameters == CHANGED
    gui.reset_parameters()
    assert_everything_is_default(pipeline)


def test_mpl_reset_parameters_resets_every_control():
    mpl_gui = pytest.importorskip("interactive_pipe.graphical.mpl_gui")
    pipeline = build_pipeline()
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipeline, name="reset")
    gui.window.refresh()
    for (filter_name, parameter), ctrl in controls_by_parameter(pipeline).items():
        ctrl.update(CHANGED[filter_name][parameter])
    assert pipeline.parameters == CHANGED
    gui.reset_parameters()
    assert_everything_is_default(pipeline)
