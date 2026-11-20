"""Video background work: read-ahead (``preload``), thumbnails built off the GUI thread, thumbnail hooks."""

import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from test_video import Burst, one_video, ramp, value  # noqa: E402

from interactive_pipe import FrameSource, Video, export_animation  # noqa: E402
from interactive_pipe.data_objects import video as video_module  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402
from interactive_pipe.headless.timeline import TimelineControl  # noqa: E402


class ThumbnailBurst(Burst):
    """A source with a cheap thumbnail (an embedded preview): the film strip never reads the frames."""

    def __init__(self, n_frames=6):
        super().__init__(n_frames)
        self.thumbnails = []

    def thumbnail(self, index):
        self.thumbnails.append(index)
        return np.full((2, 3, 3), 255, np.uint8)  # any size, uint8: shown as is


def test_frame_source_thumbnail_is_used_instead_of_the_frame():
    source = ThumbnailBurst()
    video = Video(source)
    thumb = video.thumbnail(4, height=6)
    assert thumb.shape == (6, 9, 3) and thumb.min() == 255
    assert source.thumbnails == [4] and source.reads == []
    assert Burst().thumbnail(0) is None  # the default: thumbnails come from the frames


def test_thumbnail_loader_reads_previews_of_files(tmp_path):
    for k in range(3):
        np.save(tmp_path / f"frame_{k}.npy", np.full((8, 8), k / 2, np.float32))
    loads, previews = [], []

    def loader(path):
        loads.append(path.name)
        return np.load(path)

    def thumbnail_loader(path):
        previews.append(path.name)
        return np.zeros((4, 4, 3), np.uint8)

    video = Video(tmp_path, loader=loader, thumbnail_loader=thumbnail_loader)
    assert video.thumbnail(2, 8).shape == (8, 8, 3)
    assert previews == ["frame_2.npy"] and loads == []
    assert value(video[1]) == pytest.approx(0.5) and loads == ["frame_1.npy"]
    with pytest.raises(ValueError, match="thumbnail_loader= reads files"):
        Video(ramp(3), thumbnail_loader=thumbnail_loader)
    with pytest.raises(TypeError, match="thumbnail_loader must be a function"):
        Video(tmp_path, loader=loader, thumbnail_loader="small.jpg")


def test_thumbnails_from_frames_leave_the_frame_cache_alone():
    source = Burst(6)
    video = Video(source)
    video.thumbnail(3, 8)
    assert source.reads == [3] and video.buffered() == []  # read for the thumbnail, not kept
    assert video.metadata(3) == {"iso": 400}  # its metadata is kept
    video[2]
    video.thumbnail(2, 8)
    assert source.reads == [3, 2]  # a frame in memory is not read again


def test_preload_decodes_the_next_frames_in_the_background():
    source = Burst(20)
    video = Video(source, preload=4)
    video.preload_from(5)
    assert video.wait_background()
    assert sorted(source.reads) == [6, 7, 8, 9] and video.buffered() == [6, 7, 8, 9]
    source.reads.clear()
    assert value(video[7]) == pytest.approx(0.7) and source.reads == []  # already decoded
    video.preload_from(18)  # wraps around: playback loops
    assert video.wait_background()
    assert sorted(source.reads) == [0, 1, 2, 19]
    assert Video(Burst(80), preload=50)._cache_frames >= 52  # room for the frames ahead


def test_preload_zero_never_starts_a_thread():
    video = Video(Burst(10), preload=0)
    video.preload_from(0)
    assert video._worker is None and video.buffered() == []
    with pytest.raises(ValueError, match="preload must be an int >= 0"):
        Video(ramp(3), preload=-1)
    with pytest.raises(ValueError, match="preload must be an int >= 0"):
        Video(ramp(3), preload=True)


def test_background_thread_ends_when_idle(monkeypatch):
    monkeypatch.setattr(video_module, "WORKER_IDLE_SECONDS", 0.05)
    video = Video(Burst(10), preload=2)
    video.preload_from(0)
    assert video.wait_background()
    thread = video._worker._thread
    deadline = time.monotonic() + 5
    while thread is not None and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert thread is None or not thread.is_alive()
    video.preload_from(5)  # a new request starts a new thread
    assert video.wait_background() and 6 in video.buffered()


def test_requested_thumbnails_are_built_in_the_background():
    video = Video(Burst(10))
    assert video.cached_thumbnail(3, 8) is None
    video.request_thumbnails([3, 5, 3], 8)
    assert video.wait_background()
    assert video.cached_thumbnail(3, 8) is not None and video.cached_thumbnail(5, 8) is not None
    assert video.background_version[1] == 2


class Broken(Burst):
    def read(self, index):
        if index == 2:
            raise OSError("corrupt file")
        return super().read(index)


def test_a_thumbnail_that_fails_is_not_asked_again():
    video = Video(Broken(5))
    video.request_thumbnails([2, 3], 8)
    assert video.wait_background()
    assert video.thumbnail_failed(2, 8) and video.cached_thumbnail(3, 8) is not None
    video.request_thumbnails([2], 8)
    assert video._worker is not None and video._worker._thumbnails == []


def test_videos_sharing_a_reader_share_its_lock_and_cache():
    first = Video(Burst(10))
    second = Video(first, start=2)
    assert second._lock is first._lock and second._cache is first._cache
    second[0]
    assert first.buffered() == [2] and second.buffered() == [0]
    assert first.background_version[0] == second.background_version[0]


def test_reads_from_two_threads_never_overlap():
    class Exclusive(Burst):
        def __init__(self):
            super().__init__(40)
            self.active = 0
            self.overlap = False

        def read(self, index):
            self.active += 1
            self.overlap |= self.active > 1
            time.sleep(0.001)
            self.active -= 1
            return super().read(index)

    source = Exclusive()
    video = Video(source, preload=8, cache_frames=4)
    worker = threading.Thread(target=lambda: [video.thumbnail(i, 8) for i in range(40)])
    worker.start()
    for index in range(0, 40, 3):
        video.preload_from(index)
        video[index]
    worker.join()
    assert video.wait_background() and not source.overlap


def test_timeline_preloads_every_video_at_its_own_rate():
    fast, slow = Burst(40), Burst(20)
    a, b = Video(fast, fps=20, preload=2), Video(slow, fps=10, preload=2)
    timeline = TimelineControl(40, fps=20)
    timeline.videos = [a, b]
    timeline.value = 10
    timeline.preload()
    assert a.wait_background() and b.wait_background()
    assert sorted(fast.reads) == [11, 12] and sorted(slow.reads) == [6, 7]  # frame 10 at 20 fps = frame 5 at 10 fps
    assert timeline.buffered() == [11, 12]
    assert len(timeline.background_version) == 2


def test_export_animation_reads_ahead(tmp_path):
    source = Burst(6)
    pipeline = HeadlessPipeline.from_function(one_video)
    pipeline.inputs = [Video(source, fps=6)]
    path = export_animation(pipeline, tmp_path / "clip.gif")
    assert path.exists()
    assert sorted(set(source.reads)) == list(range(6))


def test_film_strip_never_waits_for_thumbnails():
    from interactive_pipe.graphical.timeline_view import DARK, StripView

    class Strip(StripView):
        def strip_width(self):
            return 200

    source = Burst(12)
    timeline = TimelineControl(12, fps=12)
    timeline.videos = [Video(source)]
    strip = Strip()
    strip.init_strip_view(timeline)
    image = strip.strip_image(20)
    assert source.reads == [] or timeline.videos[0]._worker is not None  # asked, not read here
    pending = (image == DARK.pending).all(axis=-1).mean()
    assert pending > 0.5  # placeholder tiles meanwhile
    assert timeline.videos[0].wait_background()
    image = strip.strip_image(20)
    assert timeline.videos[0].wait_background()
    image = strip.strip_image(20)
    assert (image == DARK.pending).all(axis=-1).mean() < 0.05
    assert strip.strip_image(20, wait=True) is image  # nothing new: the composed strip is reused


def test_buffered_spans_merge_consecutive_frames():
    from interactive_pipe.graphical.timeline_view import StripView

    class Strip(StripView):
        def strip_width(self):
            return 102

    video = Video(Burst(11))
    timeline = TimelineControl(11, fps=12)
    timeline.videos = [video]
    strip = Strip()
    strip.init_strip_view(timeline)
    for index in (2, 3, 4, 8):
        video[index]
    spans = strip.buffered_spans()
    assert len(spans) == 2
    assert spans[0] == pytest.approx((16.0, 46.0)) and spans[1] == pytest.approx((76.0, 86.0))


def test_qt_timeline_preloads_and_shows_the_buffered_frames():
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    source = Burst(30)
    pipeline = HeadlessPipeline.from_function(one_video)
    gui = qt_gui.InteractivePipeQT(pipeline=pipeline, name="video preload")
    qt_gui.QTimer.singleShot(0, gui.close)
    gui(Video(source, fps=10, preload=3))
    widget = gui.window.timeline_widget
    video = pipeline.timeline.videos[0]
    widget.seek(10)
    assert video.wait_background()
    assert {11, 12, 13} <= set(video.buffered())
    widget.strip.resize(300, 64)
    assert widget.strip.buffered_spans()
    widget._background_changed()
    assert widget._background_version == pipeline.timeline.background_version
    assert not widget.strip.grab().isNull()  # paints the buffered band


def test_dpg_timeline_preloads():
    dpg_gui = pytest.importorskip("interactive_pipe.graphical.dpg_gui")
    source = Burst(30)
    pipeline = HeadlessPipeline.from_function(one_video)
    gui = dpg_gui.InteractivePipeDPG(pipeline=pipeline, name="video dpg preload")
    gui.run = lambda: None  # no viewport in tests
    gui(Video(source, fps=10, preload=3))
    panel = gui.window.timeline_panel
    video = pipeline.timeline.videos[0]
    panel.seek(10)
    assert video.wait_background()
    assert {11, 12, 13} <= set(video.buffered())
    panel.dirty = False
    panel.tick()  # the background work changed: redraw
    assert panel._background_version == pipeline.timeline.background_version


def test_frame_source_is_exported():
    assert issubclass(Burst, FrameSource)


def test_thumbnails_fill_their_tile():
    from interactive_pipe.graphical.timeline_view import _fill_width

    thumb = np.arange(4 * 6 * 3, dtype=np.uint8).reshape(4, 6, 3)
    assert _fill_width(thumb, 6) is thumb and _fill_width(thumb, 3) is thumb
    wide = _fill_width(thumb, 12)
    assert wide.shape == (4, 12, 3)
    assert (wide[:, 0] == thumb[1:3].repeat(2, axis=0)[:, 0]).all()  # enlarged x2, cropped around the centre
