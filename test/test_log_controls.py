"""Log-scale sliders and the default float step (1, 2 or 5 x 10^k)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import sys  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402

if sys.version_info >= (3, 9):
    from typing import Annotated
else:  # pragma: no cover
    from typing_extensions import Annotated

from interactive_pipe import Control, interactive  # noqa: E402
from interactive_pipe.headless.control import nice_step  # noqa: E402
from interactive_pipe.headless.explore import values_over_range  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402


@pytest.mark.parametrize(
    "span, step", [(3.0, 0.02), (98.0, 1.0), (0.71, 0.01), (19.5, 0.2), (1.0, 0.01), (0.05, 0.0005), (450.0, 5.0)]
)
def test_nice_default_step(span, step):
    assert nice_step(span) == step
    assert Control(0.0, [0.0, span]).step == step


def test_snapped_values_read_well():
    ctrl = Control(25.0, [2.0, 100.0])
    assert ctrl.step == 1.0
    assert ctrl.from_position(0.2346) == 25.0
    gain = Control(0.5, [0.1, 0.9])
    assert gain.snap(0.1 + 3 * gain.step + 1e-9) == 0.13  # no float noise


def test_log_control_positions():
    lr = Control(1e-2, [1e-4, 1e-1], scale="log")
    assert lr.is_log and lr.step is None and lr._type is float
    assert lr.to_position(1e-4) == 0.0 and lr.to_position(1e-1) == 1.0
    assert lr.to_position(1e-2) == pytest.approx(2 / 3)
    assert lr.from_position(0.5) == 0.00316  # 10 ** -2.5, 3 significant digits
    assert lr.from_position(1 / 3) == 0.001
    assert lr.from_position(2.0) == 0.1  # clamped


@pytest.mark.parametrize(
    "kwargs, message",
    [
        (dict(value_default=1e-2, value_range=[0.0, 1e-1]), "positive range"),
        (dict(value_default=1e-2, value_range=[1e-4, 1e-1], step=0.01), "no step"),
        (dict(value_default=10, value_range=[1, 100]), "float slider"),
        (dict(value_default=True), "float slider"),
    ],
)
def test_log_control_validation(kwargs, message):
    with pytest.raises(ValueError, match=message):
        Control(scale="log", **kwargs)
    with pytest.raises(ValueError, match="scale must be 'linear' or 'log'"):
        Control(1.0, [0.1, 2.0], scale="logarithmic")


@interactive(lr=(1e-2, [1e-4, 1e-1, "log"]))
def lg_shorthand(x, lr=1e-2):
    return x * lr


@interactive()
def lg_annotated(x, lr: Annotated[float, (1e-4, 1e-1, "log")] = 1e-2, gain: Annotated[float, (0.0, 3.0)] = 1.0):
    return x * lr * gain


@interactive(lr=Control(1e-2, [1e-4, 1e-1], scale="log", name="learning rate"))
def lg_explicit(x, lr=1e-2):
    return x * lr


def test_declaration_spellings():
    for func in (lg_shorthand, lg_annotated, lg_explicit):
        ctrl = Control.get_controls(func)["lr"]
        assert ctrl.is_log and ctrl.value_range == [1e-4, 1e-1] and ctrl.value_default == 1e-2
    assert not Control.get_controls(lg_annotated)["gain"].is_log
    ultra = Control.get_controls(interactive(lr=[1e-4, 1e-2, "log"])(lambda x, lr=1e-3: x))["lr"]
    assert ultra.is_log and ultra.value_default == 0.001  # geometric middle


def test_log_annotation_on_a_range_raises():
    with pytest.raises(ValueError, match="no log scale"):

        @interactive()
        def lg_bad(x, band: Annotated[tuple, (1e-4, 1e-1, "log")] = (1e-3, 1e-2)):
            return x


def lg_pipeline(x):
    y = lg_explicit(x)
    return y


def test_describe_sweep_and_tuning(tmp_path):
    pipe = HeadlessPipeline.from_function(lg_pipeline, inputs=["x"])
    entry = pipe.describe()["controls"][0]
    assert entry["scale"] == "log" and "step" not in entry
    assert "log scale" in pipe.summary()
    targets = [("lg_explicit", "lr")]
    assert values_over_range(pipe, "lr", targets, 4) == [1e-4, 1e-3, 1e-2, 1e-1]
    assert values_over_range(pipe, "lr", targets, 3) == [1e-4, 0.00316, 0.1]
    assert pipe.sweep(None, 1.0, steps={"lr": 4}).ndim == 3
    pipe.controls[0].update(0.00316)
    pipe(1.0)
    pipe.export_tuning(tmp_path / "t.yaml")
    assert "0.00316" in (tmp_path / "t.yaml").read_text()  # the real value, not a position


# --- backends: the widget moves over decades and shows / sends the real value ---


def _pipe():
    pipe = HeadlessPipeline.from_function(lg_pipeline, inputs=["x"])
    pipe.inputs = [np.ones((4, 4))]
    return pipe


def test_qt_log_slider():
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    gui = qt_gui.InteractivePipeQT(pipeline=_pipe(), name="lg qt")
    try:
        widget = gui.window.widget_list["learning rate"]
        assert widget.control_widget.value() == 667  # 1e-2 is 2/3 of the way over 3 decades
        widget.control_widget.setValue(500)
        assert gui.pipeline.controls[0].value == 0.00316
        gui.pipeline.controls[0].value = 0.1
        widget.reset()
        assert widget.control_widget.value() == 1000
    finally:
        gui.close()


def test_dpg_log_slider():
    dpg_gui = pytest.importorskip("interactive_pipe.graphical.dpg_gui")
    from interactive_pipe.graphical import dpg_backend

    dpg = pytest.importorskip("dearpygui.dearpygui")
    try:
        gui = dpg_gui.InteractivePipeDPG(pipeline=_pipe(), name="lg dpg")
        widget = gui.window.widget_list["learning rate"]
        assert dpg.get_value(widget.control_widget) == pytest.approx(2 / 3)
        widget._on_change(None, 0.5, None)
        assert gui.pipeline.controls[0].value == 0.00316
        assert dpg.get_item_configuration(widget.control_widget)["format"] == "0.00316"
    finally:
        dpg_backend.destroy_context()


def test_matplotlib_log_slider():
    mpl_gui = pytest.importorskip("interactive_pipe.graphical.mpl_gui")
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=_pipe(), name="lg mpl")
    slider = gui.window.sliders_list["learning rate"]
    assert slider.val == pytest.approx(2 / 3) and slider.valtext.get_text() == "0.01"
    slider.set_val(0.5)
    assert gui.pipeline.controls[0].value == 0.00316 and slider.valtext.get_text() == "0.00316"
    gui.close()


def test_notebook_log_slider(capsys):
    pytest.importorskip("ipywidgets")
    nb_gui = pytest.importorskip("interactive_pipe.graphical.nb_gui")
    gui = nb_gui.InteractivePipeJupyter(pipeline=_pipe(), name="lg nb")
    widget = gui.window.sliders_dict["learning rate"]
    assert type(widget).__name__ == "FloatLogSlider"
    assert (widget.min, widget.max, widget.value) == (-4.0, -1.0, 0.01)
    capsys.readouterr()


def test_gradio_log_slider(monkeypatch):
    gr = pytest.importorskip("gradio")
    monkeypatch.setattr(gr.Blocks, "launch", lambda self, *args, **kwargs: None)
    from interactive_pipe.graphical.gradio_gui import InteractivePipeGradio

    gui = InteractivePipeGradio(pipeline=_pipe(), name="lg gradio")
    gui(np.ones((4, 4)))
    (widget,) = gui.window.widget_list
    assert isinstance(widget, gr.HTML) and widget.value == 0.01
    gui.window.run_fn(0.00316)
    assert gui.pipeline.parameters["lg_explicit"]["lr"] == 0.00316
