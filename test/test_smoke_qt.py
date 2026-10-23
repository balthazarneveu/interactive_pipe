"""Qt GUI smoke tests (offscreen).

Covers window build, the layout.style -> framework_state -> title chain,
per-type parameter updates, panels/collapsible/detached windows, all
update_image branches, audio placeholders, key-event lifecycle and a full
exec() round-trip.

Runs with QT_QPA_PLATFORM=offscreen; skipped entirely when no Qt binding is
installed. Never open modal dialogs here (help/F1 would block).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")

from interactive_pipe import events, interactive, layout  # noqa: E402
from interactive_pipe.data_objects.curves import Curve, SingleCurve  # noqa: E402
from interactive_pipe.data_objects.table import Table  # noqa: E402
from interactive_pipe.headless.control import Control  # noqa: E402
from interactive_pipe.headless.panel import Panel  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

InteractivePipeQT = qt_gui.InteractivePipeQT

INPUT_IMAGE = np.linspace(0.0, 1.0, 4 * 4, dtype=np.float64).reshape(4, 4)


# ---------------------------------------------------------------------------
# Module-level filters & pipelines (the AST parser reads pipeline source)
# ---------------------------------------------------------------------------
@interactive(
    brightness=(0.5, [0.0, 1.0]),
    inverted=Control(False),
    mode=("mean", ["mean", "max"]),
    steps=(2, [0, 4]),
)
def adjust(img, brightness=0.5, inverted=False, mode="mean", steps=2):
    layout.style("adjusted", title=f"mode={mode}")
    out = img * brightness
    return 1.0 - out if inverted else out


@interactive()
def to_rgb(img):
    return np.stack([img, img, img], axis=-1)


def basic_pipeline(img):
    adjusted = adjust(img)
    rgb = to_rgb(img)
    return adjusted, rgb


@interactive()
def make_curve(img):
    return Curve([SingleCurve(y=img.mean(axis=0))], ylabel="mean")


@interactive()
def make_table(img):
    return Table(img[:2, :2], columns=["a", "b"])


@interactive()
def make_text(img):
    return f"mean={img.mean():.2f}"


def mixed_pipeline(img):
    gray = adjust(img)
    curve = make_curve(img)
    tab = make_table(img)
    txt = make_text(img)
    return [[gray, curve], [tab, txt]]


@interactive()
def make_signal(img):
    return img.flatten()


def audio_signal_pipeline(img):
    signal = make_signal(img)
    return signal


TOP_PANEL = Panel("TopTools", position="top")
LEFT_PANEL = Panel("LeftTools", position="left")
COLLAPSIBLE_PANEL = Panel("Extras", collapsible=True, collapsed=False)


@interactive(
    top_gain=Control(0.5, [0.0, 1.0], group=TOP_PANEL),
    left_gain=Control(0.5, [0.0, 1.0], group=LEFT_PANEL),
    extra_gain=Control(0.5, [0.0, 1.0], group=COLLAPSIBLE_PANEL),
)
def panel_filter(img, top_gain=0.5, left_gain=0.5, extra_gain=0.5):
    return img * top_gain * left_gain * extra_gain


def panel_pipeline(img):
    out = panel_filter(img)
    return out


DETACHED_PANEL = Panel("DetachedTools", detached=True, detached_size=(300, 200))


@interactive(detached_gain=Control(0.5, [0.0, 1.0], group=DETACHED_PANEL))
def detached_filter(img, detached_gain=0.5):
    return img * detached_gain


def detached_pipeline(img):
    out = detached_filter(img)
    return out


EVENT_LOG = []


@interactive()
def event_probe(img):
    EVENT_LOG.append(events.get("noise_evt"))
    return img


def event_pipeline(img):
    out = event_probe(img)
    return out


def build_gui(pipeline_function, **gui_kwargs):
    pipeline = HeadlessPipeline.from_function(pipeline_function, inputs=["img"])
    gui = InteractivePipeQT(pipeline=pipeline, name="smoke", **gui_kwargs)
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    return gui


# ---------------------------------------------------------------------------
# Tests. Order matters: the exec() test runs before the audio test so the
# deferred audio QTimer never fires inside a later event loop.
# ---------------------------------------------------------------------------
def test_window_builds_and_refreshes_with_styled_title():
    gui = build_gui(basic_pipeline, size=(320, 240))
    gui.window.refresh()
    canvas = gui.window.image_canvas
    assert len(canvas) == 1 and len(canvas[0]) == 2
    pixmap = canvas[0][0]["image"].pixmap()
    assert pixmap is not None and not pixmap.isNull()
    # layout.style -> global_params["__output_styles"] -> get_current_style
    assert canvas[0][0]["title"].text() == "mode=mean"
    assert canvas[0][1]["title"].text() == "rgb"  # unstyled output falls back to its name


def test_update_parameter_per_control_type():
    gui = build_gui(basic_pipeline)
    window = gui.window
    # widgets convert to the control domain before reaching update_parameter
    window.widget_list["brightness"].control_widget.setValue(1000)  # slider position -> float range max
    assert window.ctrl["brightness"].value == pytest.approx(1.0)
    window.widget_list["mode"].control_widget.setCurrentIndex(1)  # index -> choice
    assert window.ctrl["mode"].value == "max"
    window.widget_list["inverted"].control_widget.setChecked(True)
    assert window.ctrl["inverted"].value is True
    window.widget_list["steps"].control_widget.setValue(3)
    assert window.ctrl["steps"].value == 3
    # the refresh triggered by updates must propagate to the styled title
    assert window.image_canvas[0][0]["title"].text() == "mode=max"


def test_panels_by_position_and_collapsible_toggle():
    gui = build_gui(panel_pipeline)
    window = gui.window
    assert window.top_panels_layout.count() == 1
    assert window.left_panels_layout.count() == 1
    assert window.bottom_panels_layout.count() == 1  # collapsible defaults to bottom
    box = window.bottom_panels_layout.itemAt(0).widget()
    assert isinstance(box, qt_gui.CollapsibleBox)
    assert box.content_area.isVisibleTo(box)
    assert box.toggle_button.text().startswith("▼")
    box.toggle()
    assert not box.content_area.isVisibleTo(box)
    assert box.toggle_button.text().startswith("▶")


def test_detached_panel_window_lifecycle():
    gui = build_gui(detached_pipeline)
    window = gui.window
    assert len(window.detached_windows) == 1
    detached = window.detached_windows[0]
    assert detached.windowTitle() == "DetachedTools"
    detached.close()
    assert window.detached_windows == []


def test_update_image_all_branches_create_and_update():
    if not qt_gui.MPL_SUPPORT:
        pytest.skip("matplotlib support not available in qt backend")
    gui = build_gui(mixed_pipeline)
    window = gui.window
    window.refresh()  # first pass: create plot/table objects
    window.refresh()  # second pass: update path for Curve/Table
    canvas = window.image_canvas
    assert len(canvas) == 2 and len(canvas[0]) == 2
    gray_pixmap = canvas[0][0]["image"].pixmap()
    assert gray_pixmap is not None and not gray_pixmap.isNull()
    assert canvas[0][1]["plot_object"] is not None  # Curve
    assert canvas[1][0]["plot_object"] is not None  # Table
    assert canvas[1][1]["image"].text().startswith("mean=")


def test_1d_output_displays_as_curve_fallback():
    if not qt_gui.MPL_SUPPORT:
        pytest.skip("matplotlib support not available in qt backend")
    gui = build_gui(audio_signal_pipeline)
    gui.window.refresh()
    cell = gui.window.image_canvas[0][0]
    assert cell["plot_object"] is not None  # 1D ndarray warned + wrapped as Curve


def test_full_run_exec_and_quit():
    gui = build_gui(basic_pipeline)
    qt_gui.QTimer.singleShot(0, gui.close)
    results = gui(INPUT_IMAGE.copy())
    assert isinstance(results, list)


def test_context_key_event_lifecycle():
    gui = build_gui(basic_pipeline)
    gui.bind_key_to_context("n", "noise_evt", "toggle noise event")
    assert gui.pipeline.framework_state.events["noise_evt"] is False
    observed = {}

    def spy_refresh():
        observed["during_press"] = gui.pipeline.framework_state.events["noise_evt"]

    gui.on_press("n", refresh_func=spy_refresh)
    assert observed["during_press"] is True
    # reset after the press so the event only fires for one pipeline run
    assert gui.pipeline.framework_state.events["noise_evt"] is False


def test_context_key_event_visible_to_filter_through_events_proxy():
    EVENT_LOG.clear()
    gui = build_gui(event_pipeline)
    gui.bind_key_to_context("n", "noise_evt", "toggle noise event")
    gui.pipeline.run()
    # bound key pressed: the run triggered by on_press must see the flag
    gui.on_press("n", refresh_func=gui.pipeline.run)
    gui.pipeline.reset_cache()
    gui.pipeline.run()
    assert EVENT_LOG == [False, True, False]


def test_audio_placeholders_registered():
    gui = build_gui(basic_pipeline, audio=True)
    # Real audio init is deferred via QTimer (never fires without an event
    # loop): the AudioBindings no-op defaults must be in place.
    audio_bindings = gui.pipeline.framework_state.audio
    for callback in (audio_bindings.set_audio, audio_bindings.play, audio_bindings.pause, audio_bindings.stop):
        assert callable(callback)


def test_load_parameters_syncs_controls_and_widgets(tmp_path, monkeypatch):
    from interactive_pipe.data_objects.parameters import Parameters

    gui = build_gui(basic_pipeline)
    gui.window.refresh()
    tuning_path = tmp_path / "tuning.yaml"
    gui.pipeline.export_tuning(tuning_path)
    saved = Parameters.from_file(tuning_path).data
    saved["adjust"]["brightness"] = 0.25
    saved["adjust"]["mode"] = "max"
    Parameters(saved).save(tuning_path, override=True)
    monkeypatch.setattr(Parameters, "prompt_file", staticmethod(lambda *_a, **_k: str(tuning_path)))
    gui.load_parameters()
    assert gui.window.ctrl["brightness"].value == pytest.approx(0.25)
    assert gui.window.ctrl["mode"].value == "max"
    assert gui.pipeline.parameters["adjust"]["brightness"] == pytest.approx(0.25)
    # widgets follow the controls
    assert gui.window.widget_list["mode"].control_widget.currentText() == "max"
    assert gui.window.image_canvas[0][0]["title"].text() == "mode=max"


@interactive(free_int=Control(3), free_float=Control(0.5))
def free_filter(img, free_int=3, free_float=0.5):
    return img * free_float + free_int


def free_pipeline(img):
    out = free_filter(img)
    return out


def test_rangeless_numeric_controls_get_spin_boxes():
    """int/float controls without value_range used to crash the slider factory."""
    gui = build_gui(free_pipeline)
    window = gui.window
    window.refresh()
    int_box = window.widget_list["free_int"].control_widget
    float_box = window.widget_list["free_float"].control_widget
    int_box.setValue(7)
    float_box.setValue(2.25)
    assert window.ctrl["free_int"].value == 7
    assert window.ctrl["free_float"].value == pytest.approx(2.25)
    assert gui.pipeline.parameters["free_filter"] == {"free_int": 7, "free_float": pytest.approx(2.25)}
    gui.reset_parameters()
    assert int_box.value() == 3 and float_box.value() == pytest.approx(0.5)
    assert gui.pipeline.parameters["free_filter"] == {"free_int": 3, "free_float": 0.5}


@interactive(out_kind=("image", ["image", "text", "curve", "table", "signal"]))
def shape_shifter(img, out_kind="image"):
    if out_kind == "text":
        return "hello"
    if out_kind == "curve":
        return Curve([SingleCurve(y=img.mean(axis=0))])
    if out_kind == "table":
        return Table(img[:2, :2], columns=["a", "b"])
    if out_kind == "signal":
        return img.flatten()
    return img


def shape_shifter_pipeline(img):
    out = shape_shifter(img)
    return out


def test_output_type_change_between_frames_rebuilds_the_cell():
    gui = build_gui(shape_shifter_pipeline)
    window = gui.window
    window.refresh()
    canvas_widget_types = {}
    for kind in ["text", "curve", "table", "image", "signal", "text", "image", "curve", "text"]:
        window.update_parameter("out_kind", kind)
        cell = window.image_canvas[0][0]
        expected_kind = "curve" if kind == "signal" else kind
        assert cell["kind"] == expected_kind
        canvas_widget_types[kind] = type(cell["image"]).__name__
        # exactly one widget occupies the image slot of the grid
        occupants = [
            window.image_grid_layout.itemAt(i).widget()
            for i in range(window.image_grid_layout.count())
            if window.image_grid_layout.getItemPosition(i)[:2] == (1, 0)
        ]
        assert len(occupants) == 1 and occupants[0] is cell["image"]
    assert canvas_widget_types["text"] == "QLabel" and canvas_widget_types["image"] == "QLabel"
    assert canvas_widget_types["curve"] != "QLabel" and canvas_widget_types["table"] != "QLabel"
    assert window.image_canvas[0][0]["image"].text() == "hello"
