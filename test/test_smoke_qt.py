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
    window.update_parameter("brightness", 1000)  # int slider position -> float range max
    assert window.ctrl["brightness"].value == pytest.approx(1.0)
    window.update_parameter("mode", 1)  # index into value_range
    assert window.ctrl["mode"].value == "max"
    window.update_parameter("inverted", 1)
    assert window.ctrl["inverted"].value is True
    window.update_parameter("steps", 3)  # int control, direct value
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
