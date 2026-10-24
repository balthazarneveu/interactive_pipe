"""Matplotlib GUI smoke tests (Agg backend, no window shown).

Cheap coverage for the shared gui.py/window.py base classes: builds the mpl
backend, refreshes once and checks the layout.style title lands on the
axes. Never call gui.run() here (it calls plt.show and blocks).
"""

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

mpl_gui = pytest.importorskip("interactive_pipe.graphical.mpl_gui")

from interactive_pipe import interactive, layout  # noqa: E402
from interactive_pipe.headless.control import Control  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

INPUT_IMAGE = np.linspace(0.0, 1.0, 4 * 4, dtype=np.float64).reshape(4, 4)


@interactive(mpl_gain=(0.5, [0.0, 1.0]))
def mpl_adjust(img, mpl_gain=0.5):
    layout.style("adjusted", title="Adjusted!")
    return img * mpl_gain


@interactive()
def mpl_to_rgb(img):
    return np.stack([img, img, img], axis=-1)


def mpl_pipeline(img):
    adjusted = mpl_adjust(img)
    rgb = mpl_to_rgb(img)
    return adjusted, rgb


def test_window_builds_and_refreshes():
    pipeline = HeadlessPipeline.from_function(mpl_pipeline, inputs=["img"])
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipeline, name="mpl smoke")
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    gui.window.refresh()
    canvas = gui.window.image_canvas
    assert len(canvas) == 1 and len(canvas[0]) == 2
    assert canvas[0][0]["data"] is not None
    assert canvas[0][1]["data"] is not None


def test_styled_title_lands_on_axes():
    pipeline = HeadlessPipeline.from_function(mpl_pipeline, inputs=["img"])
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipeline, name="mpl smoke title")
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    gui.window.refresh()
    canvas = gui.window.image_canvas
    # layout.style -> __output_styles -> get_current_style -> ax.set_title
    assert canvas[0][0]["ax"].get_title() == "Adjusted!"
    assert canvas[0][1]["ax"].get_title() == "rgb"  # unstyled falls back to output name


def test_load_parameters_syncs_controls(tmp_path, monkeypatch):
    from interactive_pipe.data_objects.parameters import Parameters

    pipeline = HeadlessPipeline.from_function(mpl_pipeline, inputs=["img"])
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipeline, name="mpl load")
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    gui.window.refresh()
    tuning_path = tmp_path / "tuning.json"
    Parameters({"mpl_adjust": {"mpl_gain": 0.1}}).save(tuning_path)
    monkeypatch.setattr(gui, "ask_path", lambda *_a, **_k: tuning_path)
    gui.load_parameters()
    assert gui.window.ctrl["mpl_gain"].value == pytest.approx(0.1)
    assert gui.pipeline.parameters["mpl_adjust"]["mpl_gain"] == pytest.approx(0.1)
    assert gui.window.sliders_list["mpl_gain"].val == pytest.approx(0.1)
    gui.close()


@interactive(mpl_free_int=Control(3), mpl_free_float=Control(0.5))
def mpl_free_filter(img, mpl_free_int=3, mpl_free_float=0.5):
    return img * mpl_free_float + mpl_free_int


def mpl_free_pipeline(img):
    out = mpl_free_filter(img)
    return out


def test_rangeless_numeric_controls_get_text_entries():
    """int/float controls without value_range used to crash the slider factory."""
    pipeline = HeadlessPipeline.from_function(mpl_free_pipeline, inputs=["img"])
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipeline, name="mpl free")
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    gui.window.refresh()
    int_box = gui.window.sliders_list["mpl_free_int"]
    float_box = gui.window.sliders_list["mpl_free_float"]
    int_box.set_val("7")
    float_box.set_val("2.25")
    assert gui.pipeline.parameters["mpl_free_filter"] == {"mpl_free_int": 7, "mpl_free_float": pytest.approx(2.25)}
    int_box.set_val("not a number")  # rejected, value kept
    assert gui.window.ctrl["mpl_free_int"].value == 7
    gui.close()


@interactive(mpl_out_kind=("image", ["image", "text", "curve", "table", "signal"]))
def mpl_shape_shifter(img, mpl_out_kind="image"):
    from interactive_pipe.data_objects.curves import Curve, SingleCurve
    from interactive_pipe.data_objects.table import Table

    if mpl_out_kind == "text":
        return "hello"
    if mpl_out_kind == "curve":
        return Curve([SingleCurve(y=img.mean(axis=0))])
    if mpl_out_kind == "table":
        return Table(img[:2, :2], columns=["a", "b"])
    if mpl_out_kind == "signal":
        return img.flatten()
    return img


def mpl_shape_shifter_pipeline(img):
    out = mpl_shape_shifter(img)
    return out


def test_output_type_change_between_frames_rebuilds_the_axes():
    pipeline = HeadlessPipeline.from_function(mpl_shape_shifter_pipeline, inputs=["img"])
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipeline, name="mpl shapes")
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    gui.window.refresh()
    for kind in ["text", "curve", "table", "image", "signal", "signal", "text", "image", "curve", "text"]:
        gui.window.update_parameter("mpl_out_kind", kind)
        cell = gui.window.image_canvas[0][0]
        assert cell["kind"] == ("curve" if kind == "signal" else kind)
        ax = cell["ax"]
        if kind == "image":
            assert len(ax.images) == 1 and len(ax.lines) == 0
        elif kind in ("curve", "signal"):
            assert len(ax.lines) == 1 and len(ax.images) == 0
        elif kind == "text":
            assert len(ax.images) == 0 and len(ax.lines) == 0 and cell["data"].get_text() == "hello"
    gui.close()


def test_key_bindings_follow_registry_without_full_screen():
    from interactive_pipe.graphical.actions import DEFAULT_ACTIONS

    pipeline = HeadlessPipeline.from_function(mpl_pipeline, inputs=["img"])
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipeline, name="mpl keys")
    # no full screen and no zoomable image viewer on matplotlib
    expected = {action.key for action in DEFAULT_ACTIONS if action.menu != "View"}
    assert set(gui.key_bindings) == expected
    assert "f11" not in gui.key_bindings
    gui.close()
