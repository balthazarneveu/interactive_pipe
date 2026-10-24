"""Qt refresh path (offscreen): coalesced refreshes, in-window errors,
status line, View menu wiring of the image viewer and the profiling key.

Never open modal dialogs here: print_message is monkeypatched.
"""

import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")

from interactive_pipe import interactive  # noqa: E402
from interactive_pipe.core.engine import FilterError  # noqa: E402
from interactive_pipe.graphical.qt_backend import QApplication  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

INPUT_IMAGE = np.linspace(0.0, 1.0, 8 * 8, dtype=np.float64).reshape(8, 8)
SPY_CALLS = []


@interactive(gain=(0.5, [0.0, 1.0]))
def spy_gain(img, gain=0.5):
    SPY_CALLS.append(gain)
    return img * gain


@interactive(fail=(False,))
def maybe_fail(img, fail=False):
    if fail:
        raise ValueError("bad input")
    return img


@interactive()
def to_rgb_refresh(img):
    return np.stack([img, img, img], axis=-1)


SLOW_CALLS = []


@interactive(slow_gain=(0.5, [0.0, 1.0]), slow_fail=(False,))
def slow_gain_filter(img, slow_gain=0.5, slow_fail=False):
    time.sleep(0.03)
    SLOW_CALLS.append(slow_gain)
    if slow_fail:
        raise ValueError("bad input")
    return img * slow_gain


RUN_STARTED = threading.Event()
SLEEPY_ACTIVE = []  # one entry per sleepy_gain_filter call in progress
SLEEPY_OVERLAPS = []


@interactive(sleepy_gain=(0.5, [0.0, 1.0]))
def sleepy_gain_filter(img, sleepy_gain=0.5):
    SLEEPY_ACTIVE.append(sleepy_gain)
    if len(SLEEPY_ACTIVE) > 1:
        SLEEPY_OVERLAPS.append(list(SLEEPY_ACTIVE))
    RUN_STARTED.set()
    time.sleep(0.2)
    SLEEPY_ACTIVE.pop()
    return img * sleepy_gain


def sleepy_pipeline(img):
    out = sleepy_gain_filter(img)
    return out


def slow_pipeline(img):
    out = slow_gain_filter(img)
    return out


def spy_pipeline(img):
    out = spy_gain(img)
    return out


def failing_pipeline(img):
    gained = spy_gain(img)
    failed = maybe_fail(gained)
    rgb = to_rgb_refresh(gained)
    return [failed, rgb]


def build_gui(pipeline_function, **gui_kwargs):
    pipeline = HeadlessPipeline.from_function(pipeline_function, inputs=["img"])
    gui = qt_gui.InteractivePipeQT(pipeline=pipeline, name="refresh", size=(300, 200), **gui_kwargs)
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    return gui


def flush_events():
    QApplication.processEvents()


def test_parameter_updates_are_coalesced_into_one_run():
    gui = build_gui(spy_pipeline)
    window = gui.window
    window.refresh()
    SPY_CALLS.clear()
    for value in (0.1, 0.2, 0.3, 0.4):
        window.update_parameter("gain", value)
    assert SPY_CALLS == []  # nothing ran inside the widget handlers
    flush_events()
    assert SPY_CALLS == [pytest.approx(0.4)]
    flush_events()
    assert len(SPY_CALLS) == 1


def test_synchronous_refresh_cancels_the_pending_one():
    gui = build_gui(spy_pipeline)
    window = gui.window
    SPY_CALLS.clear()
    window.update_parameter("gain", 0.7)
    window.refresh()
    flush_events()
    assert SPY_CALLS == [pytest.approx(0.7)]


def test_filter_error_is_shown_in_the_window_and_recovers():
    gui = build_gui(failing_pipeline)
    window = gui.window
    window.refresh()
    assert window.last_error is None
    assert "ms" in window.status_label.text()
    window.ctrl["fail"].update(True)
    window.refresh()  # must not raise
    assert isinstance(window.last_error, FilterError)
    failing_cell = window.image_canvas[0][0]
    assert "maybe_fail" in failing_cell["image"].text()
    assert "ValueError" in failing_cell["image"].text()
    assert "error" in window.status_label.text()
    assert window.image_canvas[0][1]["image"].has_image()  # other cells kept
    window.ctrl["fail"].update(False)
    window.refresh()
    assert window.last_error is None
    assert failing_cell["image"].has_image()
    assert failing_cell["image"].styleSheet() == ""
    assert "error" not in window.status_label.text()


def test_first_run_failure_still_builds_the_canvas():
    gui = build_gui(failing_pipeline)
    window = gui.window
    window.ctrl["fail"].update(True)
    window.refresh()
    assert window.image_canvas is not None
    assert "maybe_fail" in window.image_canvas[0][0]["image"].text()


def test_hover_updates_the_status_line():
    gui = build_gui(spy_pipeline)
    window = gui.window
    window.refresh()
    view = window.image_canvas[0][0]["image"]
    view.hover_callback(3, 2, 0.25)
    assert "(3, 2) = 0.25" in window.status_label.text()
    assert "ms" in window.status_label.text()
    view.hover_callback(0, 0, None)
    assert "(3, 2)" not in window.status_label.text()
    window.set_status("custom")
    assert window.status_label.text() == "custom"


def test_view_menu_entries_call_the_window(monkeypatch):
    gui = build_gui(spy_pipeline)
    view_labels = [action.label for action in gui.actions_by_menu()["View"]]
    assert view_labels[0] == "Toggle full screen"
    assert view_labels[1:] == ["Fit to window", "Actual size 1:1", "Zoom in", "Zoom out"]
    calls = []
    monkeypatch.setattr(gui.window, "set_view_mode", lambda mode: calls.append(("mode", mode)))
    monkeypatch.setattr(gui.window, "reset_view", lambda: calls.append("reset"))
    monkeypatch.setattr(gui.window, "zoom_in", lambda: calls.append("in"))
    monkeypatch.setattr(gui.window, "zoom_out", lambda: calls.append("out"))
    for name in ("fit_view", "actual_size", "zoom_in", "zoom_out"):
        gui.menu_actions[name].trigger()
    assert calls == [("mode", "fit"), "reset", ("mode", "1:1"), "in", "out"]
    for key in ("0", "1", "+", "-"):
        gui.on_press(key)
    assert calls[5:] == [("mode", "fit"), "reset", ("mode", "1:1"), "in", "out"]


def test_t_key_prints_timings(monkeypatch):
    gui = build_gui(spy_pipeline)
    gui.window.refresh()
    messages = []
    monkeypatch.setattr(gui, "print_message", lambda lines: messages.append(lines))
    gui.on_press("t")
    assert messages and any(line.startswith("spy_gain") for line in messages[-1])


def wait_for_idle(window, timeout=5.0):
    """Process events until the worker is idle and its last result is displayed."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        QApplication.processEvents()
        if not window._runner.busy and window._displayed_seq == window._run_seq:
            return True
        time.sleep(0.005)
    return False


def test_threaded_runs_coalesce_and_display_the_latest_values():
    gui = build_gui(slow_pipeline, threaded=True)
    window = gui.window
    try:
        assert window.threaded
        window.refresh()  # synchronous initial run, as InteractivePipeQT.run does
        SLOW_CALLS.clear()
        for value in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6):
            window.update_parameter("slow_gain", value)
        assert "running" in window.status_label.text()
        assert wait_for_idle(window)
        assert SLOW_CALLS[-1] == pytest.approx(0.6)
        assert len(SLOW_CALLS) <= 3  # one run in flight + one coalesced follow-up
        assert gui.pipeline.results is not None
        assert "ms" in window.status_label.text() and "running" not in window.status_label.text()
        window.update_parameter("slow_fail", True)
        assert wait_for_idle(window)
        assert isinstance(window.last_error, FilterError)
        assert "slow_gain_filter" in window.image_canvas[0][0]["image"].text()
    finally:
        window.stop_threaded_runs()
    assert not window.threaded
    window.stop_threaded_runs()  # idempotent


def test_threaded_mode_is_off_by_default():
    gui = build_gui(spy_pipeline)
    assert not gui.window.threaded


def test_threaded_full_run_exec_and_quit_stops_the_worker():
    gui = build_gui(slow_pipeline, threaded=True)
    runner = gui.window._runner
    qt_gui.QTimer.singleShot(0, lambda: gui.window.update_parameter("slow_gain", 0.9))
    qt_gui.QTimer.singleShot(100, gui.close)
    results = gui(INPUT_IMAGE.copy())
    assert isinstance(results, list)
    assert not gui.window.threaded and not runner.isRunning()


def test_threaded_save_waits_for_the_run_and_uses_the_latest_values(tmp_path, monkeypatch):
    from interactive_pipe.data_objects.image import Image

    gui = build_gui(sleepy_pipeline, threaded=True)
    window = gui.window
    try:
        window.refresh()
        window.update_parameter("sleepy_gain", 0.7)
        assert wait_for_idle(window)
        target = tmp_path / "saved.png"
        monkeypatch.setattr(gui, "ask_path", lambda *_a, **_k: target)
        RUN_STARTED.clear()
        SLEEPY_OVERLAPS.clear()
        window.update_parameter("sleepy_gain", 0.3)  # a background run starts
        assert RUN_STARTED.wait(5.0)
        gui.save_images()  # same thread as the GUI, while the run is in flight
        assert SLEEPY_OVERLAPS == []  # the save waited for the background run
        maxima = [int(Image.load_image(path).max() * 255 + 0.5) for path in tmp_path.glob("saved_*.png")]
        assert any(abs(value - 77) <= 2 for value in maxima), maxima  # 0.3 * 255
        assert not any(abs(value - 178) <= 2 for value in maxima), maxima  # stale 0.7
        assert "0.3" in (tmp_path / "saved.yaml").read_text()
        assert wait_for_idle(window)
    finally:
        window.stop_threaded_runs()


def test_reading_the_controls_does_not_revert_a_concurrent_change(monkeypatch):
    from interactive_pipe.core.pipeline import PipelineCore

    gui = build_gui(spy_pipeline)
    control = gui.window.ctrl["gain"]
    control.update(0.3)
    original = PipelineCore.parameters

    def set_while_the_gui_changes_the_control(pipeline, new_parameters):
        control.update(0.9)  # GUI thread tick between the read and the assignment
        original.fset(pipeline, new_parameters)

    monkeypatch.setattr(PipelineCore, "parameters", property(original.fget, set_while_the_gui_changes_the_control))
    gui.pipeline.update_parameters_from_controls()
    assert control.value == pytest.approx(0.9)
    assert gui.pipeline.parameters["spy_gain"]["gain"] == pytest.approx(0.3)


def test_threaded_error_outside_the_filters_is_shown(monkeypatch):
    gui = build_gui(slow_pipeline, threaded=True)
    window = gui.window
    try:
        window.ctrl["slow_fail"].update(False)  # controls are shared with other tests
        window.refresh()

        def broken_run():
            raise KeyError("missing buffer")

        monkeypatch.setattr(gui.pipeline, "run", broken_run)
        window.update_parameter("slow_gain", 0.2)
        assert wait_for_idle(window)
        assert isinstance(window.last_error, KeyError)
        assert "running" not in window.status_label.text()
        assert "KeyError" in window.status_label.text()
        monkeypatch.undo()
        window.update_parameter("slow_gain", 0.4)
        assert wait_for_idle(window)
        assert window.last_error is None
        assert "ms" in window.status_label.text()
    finally:
        window.stop_threaded_runs()


def test_threaded_reset_runs_once_in_the_worker():
    gui = build_gui(slow_pipeline, threaded=True)
    window = gui.window
    try:
        window.ctrl["slow_fail"].update(False)  # controls are shared with other tests
        window.refresh()
        window.update_parameter("slow_gain", 0.9)
        assert wait_for_idle(window)
        SLOW_CALLS.clear()
        gui.reset_parameters()
        assert SLOW_CALLS == []  # nothing ran on the GUI thread
        assert wait_for_idle(window)
        assert SLOW_CALLS == [pytest.approx(0.5, abs=0.01)]
        assert window.ctrl["slow_gain"].value == pytest.approx(0.5, abs=0.01)
        assert window.result_label["slow_gain"].text() == f"{window.ctrl['slow_gain'].value:.3e}"
    finally:
        window.stop_threaded_runs()


def test_reset_runs_synchronously_once_when_not_threaded():
    gui = build_gui(spy_pipeline)
    window = gui.window
    window.refresh()
    window.update_parameter("gain", 0.9)
    flush_events()
    SPY_CALLS.clear()
    gui.reset_parameters()
    flush_events()
    assert SPY_CALLS == [pytest.approx(0.5, abs=0.01)]


def test_window_still_grows_after_a_failing_first_run(monkeypatch):
    gui = build_gui(failing_pipeline)
    window = gui.window
    fits = []
    monkeypatch.setattr(window, "_fit_window_to_images", lambda: fits.append(True))
    window.ctrl["fail"].update(True)
    window.refresh()
    flush_events()
    failing_cell = window.image_canvas[0][0]
    assert failing_cell.get("fit_window") is True  # not consumed by the error
    fits.clear()
    window.ctrl["fail"].update(False)
    window.refresh()
    flush_events()
    assert "fit_window" not in failing_cell
    assert fits == [True]
