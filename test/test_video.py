"""Video inputs: the ``Video`` sources, the frame filter + timeline a pipeline installs, the GUIs."""

import logging
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from interactive_pipe import (  # noqa: E402
    Timeline,
    TimelineControl,
    Video,
    context,
    export_animation,
    interactive,
    layout,
)
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402
from interactive_pipe.headless.timeline import VideoFrameFilter, timecode  # noqa: E402


def ramp(n_frames=10, height=6, width=8, channels=3):
    """Frame k is uniformly k / 10 (easy to recognise)."""
    shape = (n_frames, height, width, channels) if channels else (n_frames, height, width)
    frames = np.zeros(shape, dtype=np.float32)
    for k in range(n_frames):
        frames[k] = k / 10
    return frames


def value(frame):
    return float(np.asarray(frame).flat[0])


# --------------------------------------------------------------------- filters / pipelines
CALLS = {"amplify": 0, "reads": []}


@interactive(gain=(1.0, [0.0, 4.0]))
def amplify(img, gain=1.0):
    CALLS["amplify"] += 1
    return img * gain


@interactive()
def position(img):
    timeline = context["timeline"]
    CALLS["reads"].append(timeline)
    layout.style("pos", title=str(timeline))
    return np.full_like(img, timeline.progress)


def one_video(clip):
    out = amplify(clip)
    pos = position(clip)
    return clip, out, pos


@interactive()
def pair(a, b):
    return np.concatenate([a, b], axis=1)


def two_videos(a, b):
    both = pair(a, b)
    return both


@interactive()
def temporal_difference(frames):
    return frames[-1] - frames[0]


def windowed(frame, frames):
    diff = temporal_difference(frames)
    return frame, diff


@interactive(frame=(3, [0, 10]))
def uses_frame_name(img, frame=3):
    return img + frame


def frame_parameter(clip):
    out = uses_frame_name(clip)
    return out


# --------------------------------------------------------------------- Video sources
def test_numpy_video_frames_and_metadata():
    video = Video(ramp(10), fps=5)
    assert len(video) == 10 and video.fps == 5 and video.duration == 2.0
    assert value(video[3]) == pytest.approx(0.3)
    assert value(video[-1]) == pytest.approx(0.9)
    assert video.frame(99).shape == (6, 8, 3)  # clamped
    assert "10 frames" in repr(video)


def test_gray_numpy_video_and_slicing():
    video = Video(ramp(10, channels=0), start=2, stop=8, step=2)
    assert len(video) == 3
    assert [round(value(frame), 2) for frame in video] == [0.2, 0.4, 0.6]
    assert video.fps == 25  # no frame rate known: the default one
    assert Video(ramp(10), fps=20, step=2).fps == 20  # an explicit fps is kept


def test_window_stacks_past_frames_repeating_the_first():
    video = Video(ramp(10), window=3)
    assert video[5].shape == (3, 6, 8, 3)
    assert [round(value(frame), 1) for frame in video[5]] == [0.3, 0.4, 0.5]
    assert [round(value(frame), 1) for frame in video[0]] == [0.0, 0.0, 0.0]
    single = video.with_window(1)
    assert single._cache is video._cache and value(single[5]) == pytest.approx(0.5)


def test_list_and_generator_sources(caplog):
    frames = list(ramp(4))
    assert value(Video(frames)[2]) == pytest.approx(0.2)
    stream = Video((frame for frame in ramp(4)))
    assert len(stream) == 4
    with caplog.at_level(logging.WARNING):
        endless = Video(np.zeros((2, 2)) for _ in iter(int, 1))  # an endless stream
    assert len(endless) == 500 and "max_frames" in caplog.text
    assert len(Video((np.zeros((2, 2)) for _ in iter(int, 1)), max_frames=7)) == 7


def test_image_folder_and_glob(tmp_path):
    from interactive_pipe import Image

    for k in range(3):
        Image(np.full((4, 5, 3), k / 4)).save(tmp_path / f"f{k}.png")
    video = Video(tmp_path)
    assert len(video) == 3 and video[2].dtype == np.float32
    assert value(video[2]) == pytest.approx(0.5, abs=0.01)
    assert len(Video(str(tmp_path / "f[01].png"))) == 2
    with pytest.raises(ValueError, match="single image"):
        Video(tmp_path / "f0.png")


def test_video_file(tmp_path):
    cv2 = pytest.importorskip("cv2")
    path = tmp_path / "clip.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (16, 12))
    for k in range(6):
        writer.write(np.full((12, 16, 3), (0, 0, 40 * k), np.uint8))  # BGR: red grows
    writer.release()
    video = Video(path)
    assert len(video) == 6 and video.fps == 10
    frame = video[5]
    assert frame.shape == (12, 16, 3) and frame.dtype == np.float32
    assert frame[..., 0].mean() > 0.6 and frame[..., 2].mean() < 0.1  # RGB order
    assert value(video[1]) < value(video[4])  # a jump back seeks
    assert video.thumbnail(3, height=6).shape == (6, 8, 3)


def test_animated_gif_with_pillow(tmp_path):
    from PIL import Image as PILImage

    images = [PILImage.fromarray(np.full((8, 8, 3), 60 * k, np.uint8)) for k in range(4)]
    path = tmp_path / "anim.gif"
    images[0].save(path, save_all=True, append_images=images[1:], duration=100, loop=0)
    video = Video(path)
    assert len(video) == 4 and video.fps == pytest.approx(10)
    assert value(video[3]) == pytest.approx(180 / 255, abs=0.02)


class Tensor:
    """Stands for a torch tensor: the module and class names are what Video looks at."""

    __module__ = "torch"

    def __init__(self, array):
        self.array = np.asarray(array)
        self.ndim = self.array.ndim
        self.shape = self.array.shape

    def __len__(self):
        return len(self.array)

    def __getitem__(self, index):
        return Tensor(self.array[index])

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self.array


def test_torch_tensor_channel_first_becomes_hwc_numpy():
    tensor = Tensor(ramp(5).transpose(0, 3, 1, 2))  # (T, C, H, W)
    frame = Video(tensor)[2]
    assert isinstance(frame, np.ndarray) and frame.shape == (6, 8, 3)
    assert value(frame) == pytest.approx(0.2)
    kept = Video(tensor, to_numpy=False)[2]
    assert isinstance(kept, Tensor) and kept.shape == (3, 6, 8)


def test_real_torch_tensor():
    torch = pytest.importorskip("torch")
    frame = Video(torch.from_numpy(ramp(5).transpose(0, 3, 1, 2)))[4]
    assert isinstance(frame, np.ndarray) and frame.shape == (6, 8, 3)
    window = Video(torch.from_numpy(ramp(5)), to_numpy=False, window=2)[4]
    assert isinstance(window, torch.Tensor) and tuple(window.shape) == (2, 6, 8, 3)


@pytest.mark.parametrize(
    "source, error, match",
    [
        (np.zeros((4, 4)), ValueError, "single image is not a video"),
        ([], ValueError, "empty"),
        (42, TypeError, "unsupported source"),
        ("/no/such/file.mp4", FileNotFoundError, "does not exist"),
    ],
)
def test_bad_sources(source, error, match):
    with pytest.raises(error, match=match):
        Video(source)


def test_bad_options():
    with pytest.raises(ValueError, match="window"):
        Video(ramp(3), window=0)
    with pytest.raises(ValueError, match="no frame left"):
        Video(ramp(3), start=5)
    with pytest.raises(ValueError, match="fps"):
        Video(ramp(3), fps=0)
    with pytest.raises(ValueError, match="timeline must be one of"):
        Video(ramp(3), timeline="folded")


def test_timeline_display_comes_from_the_first_video():
    pipe = HeadlessPipeline.from_function(one_video)
    pipe(Video(ramp(5), timeline="collapsed"))
    timeline = pipe.timeline
    assert timeline.display == "collapsed" and timeline.collapsible and timeline.collapsed
    timeline.collapsed = False  # unfolded in the window: kept while the display does not change
    pipe(Video(ramp(5), timeline="collapsed"))
    assert not timeline.collapsed
    pipe(Video(ramp(5), timeline="hidden"))
    assert timeline.display == "hidden" and not timeline.collapsible
    pipe(Video(ramp(5)))
    assert timeline.display == "shown"
    assert Video(ramp(5), timeline="hidden").with_window(2).timeline_display == "hidden"


def test_video_is_never_deep_copied():
    from copy import deepcopy

    video = Video(ramp(3))
    assert deepcopy(video) is video


# --------------------------------------------------------------------- pipeline integration
def test_video_input_gets_a_frame_filter_and_a_timeline():
    pipe = HeadlessPipeline.from_function(one_video, cache=True)
    clip, out, pos = pipe(Video(ramp(10), fps=5), frame=4, gain=2.0)
    assert value(clip) == pytest.approx(0.4) and value(out) == pytest.approx(0.8)
    timeline = pipe.timeline
    assert isinstance(timeline, TimelineControl) and timeline.name == "frame"
    assert timeline.n_frames == 10 and timeline.fps == 5
    assert isinstance(pipe.filters[0], VideoFrameFilter) and pipe.filters[0].name == "video_clip"
    assert CALLS["reads"][-1] == Timeline(frame=4, n_frames=10, fps=5)
    assert pipe.styles["pos"]["title"] == "00:00.80 / 00:02.00 · frame 4/9"


def test_a_plain_input_again_removes_the_timeline():
    pipe = HeadlessPipeline.from_function(one_video)
    pipe(Video(ramp(5)))
    assert pipe.timeline is not None
    pipe.inputs = [ramp(1)[0]]
    assert pipe.timeline is None and not any(isinstance(f, VideoFrameFilter) for f in pipe.filters)
    with pytest.raises(Exception, match="timeline"):
        pipe.run()  # `position` reads context["timeline"]: only there with a video


def test_moving_the_playhead_recomputes_only_what_follows_with_the_cache():
    pipe = HeadlessPipeline.from_function(one_video, cache=True)
    video = Video(ramp(10))
    pipe(video, frame=1)
    calls = CALLS["amplify"]
    pipe(video, frame=1)  # new inputs reset the cache: everything runs
    pipe.timeline.value = 1
    pipe.run()
    assert CALLS["amplify"] == calls + 1  # same frame: cached
    pipe.timeline.value = 2
    pipe.run()
    assert CALLS["amplify"] == calls + 2
    assert "video_clip" in pipe.last_run_report.timings and "video_clip" not in pipe.last_run_report.cached


def test_two_videos_share_the_timeline_matched_by_time():
    pipe = HeadlessPipeline.from_function(two_videos)
    fast, slow = Video(ramp(10), fps=10), Video(ramp(5), fps=5)
    (both,) = pipe(fast, slow, frame=6)
    assert pipe.timeline.n_frames == 10 and pipe.timeline.fps == 10
    assert len(pipe.timeline.targets) == 2
    assert value(both[:, :8]) == pytest.approx(0.6)
    assert value(both[:, 8:]) == pytest.approx(0.3)  # 0.6 s at 5 fps: frame 3


def test_window_input_alongside_the_frame():
    pipe = HeadlessPipeline.from_function(windowed)
    data = ramp(10)
    frame, diff = pipe(Video(data), Video(data, window=3), frame=5)
    assert value(frame) == pytest.approx(0.5) and value(diff) == pytest.approx(0.2)


def test_timeline_renamed_when_a_parameter_is_called_frame():
    pipe = HeadlessPipeline.from_function(frame_parameter)
    (out,) = pipe(Video(ramp(5)), timeline=2, frame=1)
    assert pipe.timeline.name == "timeline"
    assert value(out) == pytest.approx(1.2)


def test_snapshot_sweep_describe_and_tuning(tmp_path):
    pipe = HeadlessPipeline.from_function(one_video)
    video = Video(ramp(10))
    assert pipe.snapshot(tmp_path / "s.png", video, frame=3).is_file()
    assert pipe.sweep(tmp_path / "sweep.png", video, frame=[0, 5, 9]).is_file()
    description = pipe.describe()
    entry = next(ctrl for ctrl in description["controls"] if ctrl["name"] == "frame")
    assert entry["kind"] == "timeline" and entry["n_frames"] == 10
    assert "timeline(int)" in pipe.summary() and "10 frames at 25 fps" in pipe.summary()
    pipe(video, frame=7)
    pipe.export_tuning(tmp_path / "tuning.yaml")
    pipe(video, frame=0)
    pipe.import_tuning(tmp_path / "tuning.yaml")
    assert pipe.timeline.value == 7


def test_export_animation_renders_every_frame(tmp_path):
    from PIL import Image as PILImage

    pipe = HeadlessPipeline.from_function(one_video)
    pipe(Video(ramp(6), fps=12), frame=2)
    written = export_animation(pipe, tmp_path / "clip.gif", output=0)
    gif = PILImage.open(written)
    assert gif.n_frames == 6
    assert pipe.timeline.value == 2  # restored


def test_timeline_control_steps_and_labels():
    timeline = TimelineControl(5, fps=10)
    timeline.value = 4
    assert timeline.next_frame() == 0  # loops
    timeline.loop = False
    assert timeline.next_frame() is None
    assert timeline.next_frame(-2) == 2
    assert timeline.label() == "00:00.40 / 00:00.50 · frame 4/4"
    assert timecode(3725.5) == "1:02:05.50"
    timeline.set_length(3, 5.0)
    assert timeline.value == 2 and timeline.n_frames == 3
