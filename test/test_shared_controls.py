"""One control driving several filters, and per-pipeline control state.

The same declared ``Control`` object used by several filters is one widget and
one value in a pipeline; each pipeline owns clones of the declared controls.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import json  # noqa: E402
import sys  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402

if sys.version_info >= (3, 9):
    from typing import Annotated
else:  # pragma: no cover
    from typing_extensions import Annotated

from interactive_pipe import Control, Panel, RangeControl, interactive  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

SIGNAL = np.linspace(0.0, 1.0, 11)

band = RangeControl((0.2, 0.6), [0.0, 1.0])


@interactive(band=band)
def sc_band_pass(sig, band=(0.2, 0.6)):
    lo, hi = band
    return np.where((sig >= lo) & (sig <= hi), sig, 0.0)


@interactive(bounds=band)  # another parameter name, the same control
def sc_profile(sig, bounds=(0.2, 0.6)):
    lo, hi = bounds
    return np.array([lo, hi])


def sc_pipeline(sig):
    filtered = sc_band_pass(sig)
    profile = sc_profile(sig)
    return [filtered, profile]


def _pipe():
    return HeadlessPipeline.from_function(sc_pipeline, inputs=["sig"])


def test_one_control_two_filters():
    pipe = _pipe()
    assert [ctrl.name for ctrl in pipe.controls] == ["band"]
    ctrl = pipe.controls[0]
    assert [(filt.name, param) for filt, param in ctrl.targets] == [("sc_band_pass", "band"), ("sc_profile", "bounds")]
    assert band.name == "band" and band.filter_to_connect is None  # the declaration stays untouched
    filtered, profile = pipe(SIGNAL, band=(0.1, 0.3))
    assert profile.tolist() == [0.1, 0.3]
    assert filtered[SIGNAL > 0.31].sum() == 0
    assert pipe.parameters == {"sc_band_pass": {"band": (0.1, 0.3)}, "sc_profile": {"bounds": (0.1, 0.3)}}
    ctrl.update((0.4, 0.5))  # a slider move drives both filters
    assert pipe(SIGNAL)[1].tolist() == [0.4, 0.5]


def test_one_filter_name_sets_the_shared_control():
    pipe = _pipe()
    # "filter.parameter" names one target of the shared control: it is one value
    assert pipe(SIGNAL, **{"sc_profile.bounds": (0.0, 0.9)})[1].tolist() == [0.0, 0.9]
    assert pipe.parameters["sc_band_pass"]["band"] == (0.0, 0.9)


def test_describe_lists_it_once_with_its_targets():
    pipe = _pipe()
    data = pipe.describe()
    assert [entry["name"] for entry in data["controls"]] == ["band"]
    assert data["controls"][0]["targets"] == ["sc_band_pass.band", "sc_profile.bounds"]
    assert [filt["controls"] for filt in data["filters"]] == [["band"], ["band"]]
    json.dumps(data)
    assert "-> sc_band_pass.band, sc_profile.bounds" in pipe.summary()


def test_snapshot_and_sweep_one_axis(tmp_path):
    pipe = _pipe()
    from interactive_pipe.headless.explore import _caption

    pipe.inputs = [SIGNAL]
    assert _caption(pipe, True).count("0.2") == 1  # the shared value is shown once
    assert pipe.snapshot(tmp_path / "s.png", SIGNAL, band=(0.3, 0.4)).is_file()
    image = pipe.sweep(None, SIGNAL, band=[(0.0, 0.5), (0.5, 1.0)], output="profile")
    assert image.ndim == 3
    assert pipe.controls[0].value == (0.2, 0.6)  # restored


def test_tuning_round_trip(tmp_path):
    pipe = _pipe()
    pipe.controls[0].update((0.1, 0.9))
    pipe(SIGNAL)
    pipe.export_tuning(tmp_path / "t.json")
    other = _pipe()
    assert other.controls[0].value == (0.2, 0.6)
    other.import_tuning(tmp_path / "t.json")
    assert other.controls[0].value == (0.1, 0.9)
    assert other(SIGNAL)[1].tolist() == [0.1, 0.9]


def test_two_pipelines_do_not_share_the_value():
    first, second = _pipe(), _pipe()
    first.controls[0].update((0.0, 0.1))
    assert second.controls[0].value == (0.2, 0.6)
    assert second(SIGNAL)[1].tolist() == [0.2, 0.6]
    assert sc_profile(SIGNAL).tolist() == [0.2, 0.6]  # direct call: the declared default


def test_shared_control_next_to_a_same_named_one():
    @interactive(band=(0.5, [0.0, 1.0]))
    def sc_other(sig, band=0.5):
        return sig * band

    def pipeline(sig):
        filtered = sc_band_pass(sig)
        profile = sc_profile(sig)
        scaled = sc_other(sig)
        return [filtered, profile, scaled]

    pipe = HeadlessPipeline.from_function(pipeline, inputs=["sig"])
    # the shared control keeps its name, the other one is renamed after its filter
    assert sorted(ctrl.name for ctrl in pipe.controls) == ["band", "sc_other.band"]


def test_repeated_filter_gets_its_own_shared_clone():
    def pipeline(sig):
        a = sc_band_pass(sig)
        b = sc_profile(sig)
        c = sc_band_pass(a)
        d = sc_profile(b)
        return [a, b, c, d]

    pipe = HeadlessPipeline.from_function(pipeline, inputs=["sig"])
    targets = {ctrl.name: [f"{f.name}.{p}" for f, p in ctrl.targets] for ctrl in pipe.controls}
    assert targets == {
        "band": ["sc_band_pass.band", "sc_profile.bounds"],
        "band_1": ["sc_band_pass_1.band", "sc_profile_1.bounds"],
    }


def test_different_controls_with_one_explicit_name_still_raise():
    @interactive(cut=Control(0.5, [0.0, 1.0], name="cutoff"))
    def sc_first(sig, cut=0.5):
        return sig

    @interactive(cut=Control(0.5, [0.0, 1.0], name="cutoff"))
    def sc_second(sig, cut=0.5):
        return sig

    def pipeline(sig):
        a = sc_first(sig)
        b = sc_second(a)
        return b

    with pytest.raises(ValueError, match="Duplicate control name 'cutoff'.*pass the same object"):
        HeadlessPipeline.from_function(pipeline)


Cutoff = Annotated[float, Control(0.3, [0.0, 1.0], name="cutoff")]
Gain = Annotated[float, Control(1.0, [0.0, 2.0])]


@interactive()
def sc_low(sig, cutoff: Cutoff = 0.3, gain: Gain = 1.0):
    return sig * gain


@interactive()
def sc_high(sig, fc: Cutoff = 0.3, gain: Gain = 1.0):
    return sig * gain


def test_annotation_alias_with_a_name_is_shared():
    def pipeline(sig):
        low = sc_low(sig)
        high = sc_high(sig)
        return [low, high]

    pipe = HeadlessPipeline.from_function(pipeline, inputs=["sig"])
    targets = {ctrl.name: [f"{f.name}.{p}" for f, p in ctrl.targets] for ctrl in pipe.controls}
    # named alias: one widget; unnamed alias (a reusable type): one per filter
    assert targets == {
        "cutoff": ["sc_low.cutoff", "sc_high.fc"],
        "sc_low.gain": ["sc_low.gain"],
        "sc_high.gain": ["sc_high.gain"],
    }


def test_annotation_alias_with_different_defaults_raises():
    @interactive()
    def sc_moved(sig, cutoff: Cutoff = 0.7):
        return sig

    def pipeline(sig):
        low = sc_low(sig)
        moved = sc_moved(sig)
        return [low, moved]

    with pytest.raises(ValueError, match="'cutoff' is shared by sc_low.cutoff and sc_moved.cutoff with different"):
        HeadlessPipeline.from_function(pipeline)


# --- GUI backends: one widget, driving both filters; panels list their own pipeline only ---

panel = Panel("sc settings")
level = Control(0.5, [0.0, 1.0], group=panel)


@interactive(level=level)
def sc_scale(sig, level=0.5):
    return sig * level


@interactive(amount=level)
def sc_offset(sig, amount=0.5):
    return sig + amount


def sc_gui_pipeline(sig):
    scaled = sc_scale(sig)
    shifted = sc_offset(scaled)
    return [scaled, shifted]


def _gui_pipeline():
    pipe = HeadlessPipeline.from_function(sc_gui_pipeline, inputs=["sig"])
    pipe.inputs = [SIGNAL]
    return pipe


def _check_drives_both(pipeline):
    assert pipeline.parameters == {"sc_scale": {"level": 0.25}, "sc_offset": {"amount": 0.25}}


def test_qt_one_widget_and_own_panel():
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    other = _gui_pipeline()  # another pipeline built from the same filters: its clone must not show
    gui = qt_gui.InteractivePipeQT(pipeline=_gui_pipeline(), name="sc qt")
    try:
        window = gui.window
        assert list(window.widget_list) == ["level"]
        group_boxes = [box for box in window.findChildren(qt_gui.QGroupBox) if box.title() == "sc settings"]
        assert len(group_boxes) == 1
        labels = [label.text() for label in group_boxes[0].findChildren(qt_gui.QLabel)]
        assert sum("level" in text for text in labels) == 1
        window.update_parameter("level", 0.25)
        window.refresh()
        _check_drives_both(gui.pipeline)
        assert other.controls[0].value == 0.5
    finally:
        gui.close()


def test_dpg_one_widget():
    dpg_gui = pytest.importorskip("interactive_pipe.graphical.dpg_gui")
    from interactive_pipe.graphical import dpg_backend

    _gui_pipeline()
    try:
        gui = dpg_gui.InteractivePipeDPG(pipeline=_gui_pipeline(), name="sc dpg")
        assert list(gui.window.widget_list) == ["level"]
        gui.window.update_parameter("level", 0.25)
        gui.pipeline.update_parameters_from_controls()
        _check_drives_both(gui.pipeline)
    finally:
        dpg_backend.destroy_context()


def test_gradio_one_widget(monkeypatch):
    gr = pytest.importorskip("gradio")
    monkeypatch.setattr(gr.Blocks, "launch", lambda self, *args, **kwargs: None)
    from interactive_pipe.graphical.gradio_gui import InteractivePipeGradio

    _gui_pipeline()
    gui = InteractivePipeGradio(pipeline=_gui_pipeline(), name="sc gradio")
    gui(SIGNAL)
    assert [widget.label for widget in gui.window.widget_list] == ["level"]
    gui.window.run_fn(0.25)
    _check_drives_both(gui.pipeline)


def test_matplotlib_one_slider():
    mpl_gui = pytest.importorskip("interactive_pipe.graphical.mpl_gui")
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=_gui_pipeline(), name="sc mpl")
    gui.window.refresh()
    assert list(gui.window.sliders_list) == ["level"]
    gui.window.sliders_list["level"].set_val(0.25)
    _check_drives_both(gui.pipeline)
    gui.close()


def test_notebook_one_slider(capsys):
    pytest.importorskip("ipywidgets")
    nb_gui = pytest.importorskip("interactive_pipe.graphical.nb_gui")
    gui = nb_gui.InteractivePipeJupyter(pipeline=_gui_pipeline(), name="sc nb")
    assert list(gui.window.sliders_dict) == ["level"]
    gui(SIGNAL)
    gui.window._interact_fn(level=0.25)
    _check_drives_both(gui.pipeline)
    capsys.readouterr()
