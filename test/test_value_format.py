"""Control values are written like a person would write them ("6", "0.1",
"0.005", "1e-05" only when needed), the same on Qt, Dear PyGui, matplotlib,
the notebook, Gradio and in snapshot captions (graphical/value_format.py)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from interactive_pipe import interactive  # noqa: E402
from interactive_pipe.graphical.value_format import (  # noqa: E402
    D3_FORMAT,
    JS_FORMAT_NUMBER,
    format_number,
    format_value,
    printf_format,
)
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

EXAMPLES = {
    6.0: "6",
    0.1: "0.1",
    0.005: "0.005",
    1e-05: "1e-05",
    20000.0: "20000",
    123456.7: "123457",
    1 / 3: "0.3333",
    0.1 + 0.2: "0.3",
    -0.25: "-0.25",
    0.0: "0",
    2.5e-4: "0.00025",
    1e6: "1e+06",
    1.5e7: "1.5e+07",
    9.99996: "10",
}


@pytest.mark.parametrize("value, text", list(EXAMPLES.items()))
def test_format_number(value, text):
    assert format_number(value) == text


def test_integers_booleans_and_numpy_scalars():
    assert format_number(3) == "3"
    assert format_number(np.int64(4)) == "4"
    assert format_number(np.float32(0.1)) == "0.1"
    assert format_number(True) == "True"
    assert format_value((0.1, 2.0)) == "(0.1, 2)"
    assert format_value("median") == "median"
    assert format_value(np.int64(3)) == "3" and format_value(True) == "True"


@pytest.mark.parametrize(
    "value", [*EXAMPLES, 1e-3, 0.0123456, 7.5, 999.95, 1e-4, 99999.99, -3e-7, 4.2e9, float("nan"), float("inf")]
)
def test_printf_format_gives_the_same_text(value):
    """Dear PyGui formats natively with printf_format: same text."""
    text = printf_format(value) % value
    assert ("0" if text in ("-0", "-0.0") else text) == format_number(value)


def test_js_and_d3_formats():
    assert JS_FORMAT_NUMBER.startswith("const fmt = (v) =>")
    assert D3_FORMAT == ".6"


# ---------------------------------------------------------------------------
# Each backend
# ---------------------------------------------------------------------------


@interactive(gain=(6.0, [0.0, 20.0]), sigma=(0.1, [0.0, 1.0]))
def adjust(img, gain=6.0, sigma=0.1):
    return np.clip(img * gain * (1 + sigma), 0.0, 1.0)


def value_pipeline(img):
    out = adjust(img)
    return out


IMG = np.full((8, 8, 3), 0.01)


def test_qt_value_labels():
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    pipe = HeadlessPipeline.from_function(value_pipeline, inputs=["img"])
    gui = qt_gui.InteractivePipeQT(pipeline=pipe, name="values")
    try:
        gui.pipeline.inputs = [IMG]
        window = gui.window
        texts = {name: label.text() for name, label in window.result_label.items()}
        assert sorted(texts.values()) == ["0.1", "6"]
    finally:
        gui.close()


def test_dpg_slider_format():
    dpg_gui = pytest.importorskip("interactive_pipe.graphical.dpg_gui")
    import dearpygui.dearpygui as dpg

    from interactive_pipe.graphical import dpg_backend

    try:
        pipe = HeadlessPipeline.from_function(value_pipeline, inputs=["img"])
        gui = dpg_gui.InteractivePipeDPG(pipeline=pipe, name="values dpg")
        window = gui.window

        def shown():
            texts = {}
            for name, wrapper in window.widget_list.items():
                widget = wrapper.control_widget
                texts[name] = dpg.get_item_configuration(widget)["format"] % dpg.get_value(widget)
            return sorted(texts.values())

        assert shown() == sorted(format_number(w.ctrl.value) for w in window.widget_list.values())
        sigma = next(w for w in window.widget_list.values() if w.ctrl.value_range[1] == 1.0)
        sigma._on_change(None, 0.37, None)  # a slider move (snapped to the step)
        value = dpg.get_value(sigma.control_widget)
        assert dpg.get_item_configuration(sigma.control_widget)["format"] % value == format_number(value)
        sigma._on_change(None, 0.1, None)  # controls are shared with the other tests
        assert shown() == ["0.1", "6"]
    finally:
        dpg_backend.destroy_context()


def test_mpl_slider_text():
    mpl_gui = pytest.importorskip("interactive_pipe.graphical.mpl_gui")

    pipe = HeadlessPipeline.from_function(value_pipeline, inputs=["img"])
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipe, name="values mpl")
    try:
        gui.pipeline.inputs = [IMG]
        sliders = list(gui.window.sliders_list.values())
        assert sorted(slider.valtext.get_text() for slider in sliders) == ["0.1", "6"]
        gain = next(slider for slider in sliders if slider.valmax == 20.0)
        gain.set_val(12.5)
        assert gain.valtext.get_text() == "12.5"
    finally:
        gui.close()


def test_notebook_slider_readout_format():
    nb_control = pytest.importorskip("interactive_pipe.graphical.nb_control")
    pytest.importorskip("ipywidgets")
    from interactive_pipe.headless.control import Control

    widget = nb_control.FloatSliderNotebookControl("sigma_nb", Control(0.1, [0.0, 1.0], name="sigma_nb")).create()
    assert widget.readout_format == D3_FORMAT


def test_snapshot_caption():
    from interactive_pipe.headless.snapshot import format_value

    assert format_value(6.0) == "6"
    assert format_value(1e-05) == "1e-05"
    assert format_value(20000.0) == "20000"


@pytest.mark.parametrize("value", [0.005, 0.003162, 12.5, 1e-05, 2.5e07, 90.0])
def test_dpg_log_slider_and_dial_texts_use_the_shared_formatter(value):
    from types import SimpleNamespace

    dpg_control = pytest.importorskip("interactive_pipe.graphical.dpg_control")
    assert dpg_control._log_label(value) % () == format_number(value)
    dial = SimpleNamespace(ctrl=SimpleNamespace(_type=float), value=value)
    assert dpg_control.DialControl._label(dial) == format_number(value)
