"""A ``Video`` returned by a filter: the frame filter put after it, the timeline it brings, the GUIs."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from interactive_pipe import Video, context, interactive  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402
from interactive_pipe.headless.timeline import GeneratedVideoFrameFilter  # noqa: E402

CALLS = {"make": 0, "shade": 0}


@interactive(n=(4, [1, 10]), fps=(3.0, [1.0, 10.0]), as_video=(True,))
def make(n=4, fps=3.0, as_video=True):
    """Frame k is uniformly k / 10; ``as_video=False`` returns the first frame alone."""
    CALLS["make"] += 1
    frames = np.stack([np.full((4, 6, 3), k / 10, np.float32) for k in range(n)])
    return Video(frames, fps=fps) if as_video else frames[0]


@interactive(gain=(1.0, [0.0, 2.0]))
def shade(img, gain=1.0):
    CALLS["shade"] += 1
    timeline = context.get("timeline")
    return img * gain, np.full((4, 6, 3), -1 if timeline is None else timeline.frame / 10, np.float32)


def generated():
    clip = make()
    out, pos = shade(clip)
    return out, pos


def value(frame):
    return float(np.asarray(frame).flat[0])


@pytest.fixture(autouse=True)
def reset_calls():
    CALLS.update(make=0, shade=0)


@pytest.mark.parametrize("cache", ["graph", True, False])
def test_filter_returning_a_video_brings_the_timeline(cache):
    pipeline = HeadlessPipeline.from_function(generated, cache=cache)
    assert pipeline.timeline is None  # nothing known before a run
    out, pos = pipeline.run()
    names = [filt.name for filt in pipeline.filters]
    assert names == ["make", "video_clip", "shade"]  # the frame filter right after the filter making the video
    assert isinstance(pipeline.filters[1], GeneratedVideoFrameFilter)
    timeline = pipeline.timeline
    assert timeline is not None and timeline.n_frames == 4 and timeline.fps == 3.0
    assert timeline.track_names == ["clip"] and len(timeline.videos) == 1  # one film strip lane
    assert value(out) == 0.0 and value(pos) == 0.0
    timeline.value = 2
    out, pos = pipeline.run()
    assert value(out) == pytest.approx(0.2) and value(pos) == pytest.approx(0.2)
    if cache:
        assert CALLS["make"] == 1  # the playhead never runs the filter making the video again
    assert len(pipeline.filters) == 3  # inserted once


def test_timeline_follows_the_generated_video():
    pipeline = HeadlessPipeline.from_function(generated, cache="graph")
    pipeline.run()
    timeline = pipeline.timeline
    pipeline.parameters = {"make": {"n": 8, "fps": 6.0}}
    pipeline.run()
    assert timeline.n_frames == 8 and timeline.fps == 6.0 and pipeline.timeline is timeline
    timeline.value = 7
    out, _ = pipeline.run()
    assert value(out) == pytest.approx(0.7)
    pipeline.parameters = {"make": {"n": 3}}
    out, _ = pipeline.run()
    assert timeline.n_frames == 3 and timeline.value == 2  # clamped to the shorter video
    assert value(out) == pytest.approx(0.2)
    calls = CALLS["make"]
    pipeline.parameters = {"shade": {"gain": 2.0}}
    out, _ = pipeline.run()
    assert CALLS["make"] == calls and value(out) == pytest.approx(0.4)


def test_filter_stops_returning_a_video():
    pipeline = HeadlessPipeline.from_function(generated, cache="graph")
    pipeline.run()
    pipeline.parameters = {"make": {"as_video": False}}
    out, _ = pipeline.run()  # the frame filter lets the array through
    assert value(out) == 0.0 and out.shape == (4, 6, 3)


def test_dpg_window_gains_the_timeline_after_the_first_run():
    dpg_gui = pytest.importorskip("interactive_pipe.graphical.dpg_gui")
    pipeline = HeadlessPipeline.from_function(generated, cache="graph")
    gui = dpg_gui.InteractivePipeDPG(pipeline=pipeline, name="generated video dpg")
    gui.run = lambda: None  # no viewport in tests
    gui()
    window = gui.window
    assert window.timeline_panel is None
    window.refresh()  # the first run: a filter returns a Video
    panel = window.timeline_panel
    assert panel is not None and window.widget_list["frame"] is panel
    gui.on_press("right")  # the timeline keys are bound
    assert pipeline.timeline.value == 1
    window.refresh()
    assert CALLS["make"] == 1
    gui.close()


def test_qt_window_gains_the_timeline_after_the_first_run():
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    pipeline = HeadlessPipeline.from_function(generated, cache="graph")
    gui = qt_gui.InteractivePipeQT(pipeline=pipeline, name="generated video qt")
    qt_gui.QTimer.singleShot(0, gui.close)
    gui()
    widget = gui.window.timeline_widget
    assert gui.window.ctrl["frame"] is pipeline.timeline
    assert widget.frame_label.text() == "frame 0 / 3"
    gui.on_press("right")
    assert pipeline.timeline.value == 1


def test_qt_timeline_shows_the_new_length_after_a_slider_run():
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    pipeline = HeadlessPipeline.from_function(generated, cache="graph")
    gui = qt_gui.InteractivePipeQT(pipeline=pipeline, name="generated video qt resize")
    labels = []

    def resize_then_close():
        window = gui.window
        for ctrl in window.ctrl.values():
            if getattr(ctrl, "parameter_name_to_connect", None) == "n":
                ctrl.update(8)
        window.refresh()  # the slider of the filter making the video: no playhead move
        labels.append(window.timeline_widget.frame_label.text())
        gui.close()

    qt_gui.QTimer.singleShot(0, resize_then_close)
    gui()
    assert labels == ["frame 0 / 7"]


def test_dpg_timeline_redraws_after_the_video_changes_length():
    dpg_gui = pytest.importorskip("interactive_pipe.graphical.dpg_gui")
    pipeline = HeadlessPipeline.from_function(generated, cache="graph")
    gui = dpg_gui.InteractivePipeDPG(pipeline=pipeline, name="generated video dpg resize")
    gui.run = lambda: None
    gui()
    window = gui.window
    window.refresh()
    panel = window.timeline_panel
    panel.dirty = False
    window.refresh()  # same video
    assert not panel.dirty
    pipeline.parameters = {"make": {"n": 8}}
    window.refresh()
    assert panel.dirty and pipeline.timeline.n_frames == 8
    gui.close()
