"""Point / region controls without mouse gestures: one slider per coordinate, on every backend.

Backends that handle the mouse set ``pointer_gestures = True``; here each one
is forced back to the default (False) to check that the fallback goes through
its widget factory, as it would for an unknown future backend.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from interactive_pipe import Panel, PointControl, RegionControl, interactive, to_pixels  # noqa: E402
from interactive_pipe.graphical.gui import InteractivePipeGUI  # noqa: E402
from interactive_pipe.graphical.pointer_input import controls_for_backend  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402
from interactive_pipe.headless.pointer import PointerAxisControl  # noqa: E402

IMAGE = np.zeros((20, 40, 3))
SLIDERS = ["fb_seed x", "fb_seed y", "fb_roi x0", "fb_roi y0", "fb_roi x1", "fb_roi y1"]


@interactive(
    fb_seed=PointControl((0.5, 0.5), name="fb_seed"),
    fb_roi=RegionControl((0.25, 0.25, 0.75, 0.75), name="fb_roi"),
)
def fb_probe(img, fb_seed=(0.5, 0.5), fb_roi=(0.25, 0.25, 0.75, 0.75)):
    col, row = to_pixels(fb_seed, img)
    x0, y0, x1, y1 = to_pixels(fb_roi, img)
    out = img.copy()
    out[y0:y1, x0:x1] = 0.5
    out[row, col] = 1.0
    return out


def fb_pipeline(img):
    probed = fb_probe(img)
    return probed


def _pipeline():
    pipeline = HeadlessPipeline.from_function(fb_pipeline, inputs=["img"])
    for ctrl in pipeline.controls:
        ctrl.update(ctrl.value_default)
    return pipeline


def _marked_pixel(pipeline):
    out = pipeline.results
    while isinstance(out, (list, tuple)):  # GUIs give a grid
        out = out[0]
    return np.argwhere(out[..., 0] == 1.0).tolist()


class MinimalBackend(InteractivePipeGUI):
    """What a new backend looks like before it knows about pointer controls."""

    def init_app(self, **kwargs):
        pass

    def run(self):
        return self.pipeline.run()


def test_unknown_backend_gets_sliders():
    gui = MinimalBackend(pipeline=_pipeline())
    assert [ctrl.name for ctrl in gui.controls] == SLIDERS
    assert all(isinstance(ctrl, PointerAxisControl) for ctrl in gui.controls)
    assert all(ctrl._type is float and ctrl.value_range == [0.0, 1.0] for ctrl in gui.controls)
    gui.controls[0].update(0.0)
    gui.controls[1].update(0.0)
    gui(IMAGE)
    assert _marked_pixel(gui.pipeline) == [[0, 0]]


def test_unknown_target_fails_when_the_gui_is_built():
    @interactive(fb_where=PointControl((0.5, 0.5), on="nope", name="fb_where"))
    def fb_misplaced(img, fb_where=(0.5, 0.5)):
        return img

    def bad_pipeline(img):
        out = fb_misplaced(img)
        return out

    with pytest.raises(ValueError, match=r"on='nope' is not an output .*Available outputs: \['out'\]"):
        MinimalBackend(pipeline=HeadlessPipeline.from_function(bad_pipeline, inputs=["img"]))


def test_panel_lists_the_sliders_in_place_of_the_control_and_back():
    panel = Panel("probe panel")
    before = PointControl((0.5, 0.5), name="before_ctrl")  # unconnected, only its panel matters
    point = PointControl((0.2, 0.3), name="p", group=panel)
    after = RegionControl((0.1, 0.1, 0.2, 0.2), name="r", group=panel)
    assert panel._controls == [point, after]
    shown = controls_for_backend([before, point, after], gestures=False)
    names = [ctrl.name for ctrl in shown]
    assert names == ["before_ctrl x", "before_ctrl y", "p x", "p y", "r x0", "r y0", "r x1", "r y1"]
    assert [ctrl.name for ctrl in panel._controls] == ["p x", "p y", "r x0", "r y0", "r x1", "r y1"]
    assert all(ctrl.panel is panel for ctrl in panel._controls)
    # a gesture backend built later gets the controls back
    assert controls_for_backend([point, after], gestures=True) == [point, after]
    assert panel._controls == [point, after]


def _no_gestures(cls):
    return type(f"NoGesture{cls.__name__}", (cls,), {"pointer_gestures": False})


def test_matplotlib_fallback_sliders():
    mpl_gui = pytest.importorskip("interactive_pipe.graphical.mpl_gui")
    gui = _no_gestures(mpl_gui.InteractivePipeMatplotlib)(pipeline=_pipeline(), name="fb mpl")
    gui.pipeline.inputs = [IMAGE]
    gui.window.refresh()
    assert list(gui.window.sliders_list) == SLIDERS
    gui.window.sliders_list["fb_seed x"].set_val(0.0)
    assert gui.window.ctrl["fb_seed x"].parent.value == (0.0, 0.5)
    assert _marked_pixel(gui.pipeline) == [[10, 0]]
    gui.reset_parameters()
    assert gui.pipeline.parameters["fb_probe"]["fb_seed"] == (0.5, 0.5)
    gui.close()


def test_qt_fallback_sliders():
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    gui = _no_gestures(qt_gui.InteractivePipeQT)(pipeline=_pipeline(), name="fb qt")
    gui.pipeline.inputs = [IMAGE]
    window = gui.window
    assert SLIDERS == [name for name in window.widget_list if name.startswith("fb_")]
    window.update_parameter("fb_seed y", 0.0)
    window.refresh()
    assert _marked_pixel(gui.pipeline) == [[0, 20]]
    gui.reset_parameters()
    assert window.ctrl["fb_seed y"].value == 0.5
    assert gui.pipeline.parameters["fb_probe"]["fb_seed"] == (0.5, 0.5)
    gui.close()


def test_dpg_fallback_sliders():
    dpg_gui = pytest.importorskip("interactive_pipe.graphical.dpg_gui")
    from interactive_pipe.graphical import dpg_backend

    try:
        gui = _no_gestures(dpg_gui.InteractivePipeDPG)(pipeline=_pipeline(), name="fb dpg")
        gui.pipeline.inputs = [IMAGE]
        assert SLIDERS == [name for name in gui.window.widget_list if name.startswith("fb_")]
        gui.window.update_parameter("fb_roi x1", 0.3)
        assert gui.pipeline.parameters["fb_probe"]["fb_roi"] == (0.25, 0.25, 0.3, 0.75)
    finally:
        dpg_backend.destroy_context()


def test_gradio_fallback_sliders(monkeypatch):
    gr = pytest.importorskip("gradio")
    monkeypatch.setattr(gr.Blocks, "launch", lambda self, *args, **kwargs: None)
    from interactive_pipe.graphical.gradio_gui import InteractivePipeGradio

    gui = _no_gestures(InteractivePipeGradio)(pipeline=_pipeline(), name="fb gradio")
    gui(IMAGE)
    window = gui.window
    assert [widget.label for widget in window.widget_list] == SLIDERS
    window.run_fn(0.0, 0.0, 0.25, 0.25, 0.75, 0.75)
    assert gui.pipeline.parameters["fb_probe"]["fb_seed"] == (0.0, 0.0)


def test_notebook_fallback_sliders(capsys):
    pytest.importorskip("ipywidgets")
    nb_gui = pytest.importorskip("interactive_pipe.graphical.nb_gui")
    gui = nb_gui.InteractivePipeJupyter(pipeline=_pipeline(), name="fb nb")
    widgets = gui.window.sliders_dict
    assert list(widgets) == SLIDERS
    assert type(widgets["fb_seed x"]).__name__ == "FloatSlider"
    gui(IMAGE)
    gui.window._interact_fn(**{"fb_seed x": 0.0, "fb_seed y": 1.0})
    assert gui.pipeline.parameters["fb_probe"]["fb_seed"] == (0.0, 1.0)
    capsys.readouterr()
