"""Webcam inputs: the frame filter and live clock a pipeline installs, headless
reads, the Qt live refresh and freeze. No real camera: fake sources only."""

import itertools
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from interactive_pipe import Webcam, interactive, interactive_pipeline  # noqa: E402
from interactive_pipe.graphical.gui import InteractivePipeGUI  # noqa: E402
from interactive_pipe.headless.live import LiveControl, WebcamFrameFilter, live_clock_of  # noqa: E402


def counting_source(shape=(4, 6, 3)):
    """A function source: frame k is filled with k (uint8)."""
    counter = itertools.count()
    return lambda: np.full(shape, next(counter), np.uint8)


class FakeCapture:
    """cv2.VideoCapture-like: read() -> (ok, BGR frame)."""

    def __init__(self):
        self.reads = 0
        self.released = False

    def read(self):
        self.reads += 1
        frame = np.zeros((2, 3, 3), np.uint8)
        frame[..., 0] = 10  # blue
        frame[..., 2] = 200  # red
        return True, frame

    def release(self):
        self.released = True


@interactive(gain=(1.0, [0.0, 2.0]))
def webcam_gain(frame, gain=1.0):
    return frame * gain


@interactive_pipeline(gui=None)
def live_pipe(frame):
    out = webcam_gain(frame)
    return frame, out


def test_headless_reads_a_new_frame_per_run():
    cam = Webcam(counting_source(), warmup=0)
    first = live_pipe(cam)
    second = live_pipe(cam, gain=0.5)
    assert first[0][0, 0, 0] == pytest.approx(0.0)
    assert second[0][0, 0, 0] == pytest.approx(1 / 255)
    assert second[1][0, 0, 0] == pytest.approx(0.5 / 255)
    assert second[0].dtype == np.float32


def test_pipeline_installs_one_filter_and_clock():
    cam = Webcam(counting_source(), warmup=0)
    live_pipe(cam)
    live_pipe(cam)  # idempotent
    filters = [filt for filt in live_pipe.filters if isinstance(filt, WebcamFrameFilter)]
    assert [filt.name for filt in filters] == ["webcam_frame"]
    clock = live_clock_of(live_pipe)
    assert isinstance(clock, LiveControl) and clock.name == "live" and clock.webcams == [cam]
    assert clock.update_interval_ms == 33
    assert [filt for filt, _ in clock.targets] == filters
    data = live_pipe.describe()
    assert [ctrl["kind"] for ctrl in data["controls"] if ctrl["name"] == "live"] == ["live"]


def test_plain_image_after_webcam_removes_the_filter():
    @interactive_pipeline(gui=None)
    def reused(frame):
        out = webcam_gain(frame)
        return out

    reused(Webcam(counting_source(), warmup=0))
    image = np.ones((2, 2, 3), np.float32)
    assert np.allclose(reused(image), image)
    assert not any(isinstance(filt, WebcamFrameFilter) for filt in reused.filters)
    assert live_clock_of(reused) is None
    assert np.allclose(reused(image), image)


def test_capture_source_is_converted_to_rgb_float_and_mirrored():
    capture = FakeCapture()
    cam = Webcam(capture, mirror=True, warmup=2)
    frame = cam.read()
    assert capture.reads == 3  # two warm-up frames dropped
    assert frame.shape == (2, 3, 3)
    assert np.allclose(frame[0, 0], [200 / 255, 0, 10 / 255])
    cam.release()
    assert not capture.released  # opened by the caller: released by the caller


def test_uint8_frames_kept_without_as_float():
    cam = Webcam(counting_source(), as_float=False, warmup=0)
    assert cam.read().dtype == np.uint8


def test_function_returning_none_repeats_the_previous_frame():
    frames = iter([np.zeros((2, 2)), None])
    cam = Webcam(lambda: next(frames), warmup=0)
    first = cam.read()
    assert cam.read() is first


def test_generator_is_a_frame_source_and_keeps_the_last_frame_when_exhausted():
    def frames():
        yield np.zeros((2, 2))
        yield np.ones((2, 2))

    cam = Webcam(frames(), warmup=0)
    assert cam.is_function
    assert cam.description == "frames"
    assert cam.read().max() == 0
    last = cam.read()
    assert last.max() == 1
    assert cam.read() is last  # exhausted: no new frame, the previous one stays


def test_plain_iterator_is_a_frame_source():
    cam = Webcam(iter([np.full((2, 2), 3.0)]), warmup=0)
    assert cam.read()[0, 0] == 3.0


@pytest.mark.parametrize(
    "kwargs, error",
    [
        ({"device": 1.5}, TypeError),
        ({"device": True}, TypeError),
        ({"fps": 0}, ValueError),
        ({"width": -1}, ValueError),
        ({"warmup": -1}, ValueError),
    ],
)
def test_invalid_arguments(kwargs, error):
    with pytest.raises(error):
        Webcam(**kwargs)


def test_missing_camera_names_the_fix():
    pytest.importorskip("cv2")
    with pytest.raises(RuntimeError, match="cannot open"):
        Webcam("/nonexistent/video99").open()


def test_background_reader_gives_the_latest_frame_and_idles_out(monkeypatch):
    import interactive_pipe.data_objects.webcam as webcam_module

    monkeypatch.setattr(webcam_module, "READER_IDLE_SECONDS", 0.2)
    cam = Webcam(counting_source(), fps=200, warmup=0)
    first = cam.latest()
    time.sleep(0.1)
    later = cam.latest()
    assert later[0, 0, 0] > first[0, 0, 0]
    time.sleep(0.5)  # nobody asks: the reader stops
    assert not cam._reader_alive()
    cam.release()


def test_frame_filter_keeps_the_tick_frame_when_ticking():
    cam = Webcam(counting_source(), fps=200, warmup=0)
    clock = LiveControl(cam.fps)
    filt = WebcamFrameFilter("frame", "webcam_frame", clock)
    clock.ticking = True
    frozen = filt.apply(cam, live_tick=1.0)
    time.sleep(0.05)
    assert filt.apply(cam, live_tick=1.0) is frozen  # same tick (frozen feed, slider moved)
    assert filt.apply(cam, live_tick=2.0)[0, 0, 0] > frozen[0, 0, 0]
    cam.release()


def test_snapshot_caption_leaves_the_clock_out(tmp_path):
    cam = Webcam(counting_source(), warmup=0)
    live_pipe.snapshot(tmp_path / "shot.png", cam, gain=1.5)
    from interactive_pipe.headless.explore import _caption

    caption = _caption(live_pipe, True)
    assert "live_tick" not in caption and "webcam_gain: gain=" in caption


class _NoTimerGUI:
    live_clock = False
    pointer_gestures = False


def test_backends_without_timer_show_no_clock():
    clock = LiveControl(30.0)
    assert InteractivePipeGUI._backend_controls(_NoTimerGUI(), [clock]) == []  # type: ignore[arg-type]
    _NoTimerGUI.live_clock = True
    try:
        assert InteractivePipeGUI._backend_controls(_NoTimerGUI(), [clock]) == [clock]  # type: ignore[arg-type]
    finally:
        _NoTimerGUI.live_clock = False


def test_qt_window_refreshes_live_and_freezes():
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    calls = []

    @interactive(qt_gain=(1.0, [0.0, 2.0]))
    def qt_spy(frame, qt_gain=1.0):
        calls.append((float(frame[0, 0, 0]), qt_gain))
        return frame * qt_gain

    @interactive_pipeline(gui=None)
    def qt_live(frame):
        out = qt_spy(frame)
        return out

    gui = qt_gui.InteractivePipeQT(pipeline=qt_live, name="webcam", size=(200, 150))
    marks = {}

    def freeze():
        marks["freeze"] = len(calls)
        gui.on_press(" ")

    def move_slider():
        marks["slider"] = len(calls)
        gui.window.update_parameter("qt_gain", 1.5)

    def resume():
        marks["resume"] = len(calls)
        gui.on_press(" ")

    qt_gui.QTimer.singleShot(400, freeze)
    qt_gui.QTimer.singleShot(500, move_slider)
    qt_gui.QTimer.singleShot(700, resume)
    qt_gui.QTimer.singleShot(1000, gui.close)
    gui(Webcam(counting_source(), warmup=0))

    live_frames = {value for value, _ in calls[: marks["freeze"]]}
    assert len(live_frames) >= 3  # new frames while live
    frozen = calls[marks["freeze"] : marks["resume"]]
    assert frozen and frozen[-1][1] == 1.5  # the slider re-ran the pipeline...
    assert len({value for value, _ in frozen}) == 1  # ...on the frozen frame
    assert len({value for value, _ in calls[marks["resume"] :]}) >= 2  # live again
