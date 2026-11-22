"""AudioClip inputs: the whole signal for the filters, a timeline (waveform lane), the sound following it."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import wave  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from interactive_pipe import AudioClip, Video, audio, context, interactive  # noqa: E402
from interactive_pipe.core.audio_mixer import SignalMixer  # noqa: E402
from interactive_pipe.core.framework_state import AudioRequest  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402
from interactive_pipe.headless.timeline import (  # noqa: E402
    AUDIO_TIMELINE_FPS,
    AudioClipFilter,
    TimelineClockFilter,
    VideoFrameFilter,
)

RATE = 8000
CALLS = []


def tone(seconds=2.0, amplitude=0.5, rate=RATE):
    t = np.arange(int(seconds * rate)) / rate
    return (amplitude * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


@interactive(gain=(1.0, [0.0, 2.0]))
def amplify(signal, gain=1.0):
    CALLS.append("amplify")
    return signal * gain


@interactive()
def where(signal):
    CALLS.append("where")
    return np.array([context["timeline"].time], np.float32)


def one_sound(sound):
    louder = amplify(sound)
    position = where(louder)
    return louder, position


@interactive(mix=(0.5, [0.0, 1.0]))
def blend(a, b, mix=0.5):
    n = max(len(a), len(b))
    return (1 - mix) * np.pad(a, (0, n - len(a))) + mix * np.pad(b, (0, n - len(b)))


def two_sounds(a, b):
    mixed = blend(a, b)
    return mixed


@interactive()
def frame_and_rate(frame, sound):
    rate = context["timeline"].inputs_metadata["sound"]["sample_rate"]
    return np.full(frame.shape[:2], rate / RATE, np.float32)


def video_and_sound(frame, sound):
    out = frame_and_rate(frame, sound)
    return out


# ---------------------------------------------------------------- AudioClip
def test_audio_clip_from_a_signal():
    clip = AudioClip(tone(1.5), RATE)
    assert len(clip) == 12000 and clip.duration == 1.5 and clip.channels == 1
    assert clip.metadata() == {"sample_rate": RATE, "duration": 1.5, "channels": 1}
    assert repr(clip) == "AudioClip(signal, 1.50 s at 8000 Hz)"
    pcm = (tone(0.5) * 32767).astype(np.int16)
    assert AudioClip(pcm, RATE).signal.dtype == np.float32
    stereo = AudioClip(np.stack([tone(1.0), tone(1.0)], axis=1), RATE)
    assert stereo.channels == 2 and "2 channels" in repr(stereo)


def test_audio_clip_rejects_what_it_cannot_play():
    with pytest.raises(TypeError, match="needs its sample rate"):
        AudioClip(tone())
    with pytest.raises(ValueError, match="channels go last"):
        AudioClip(np.zeros((2, 100), np.float32), RATE)
    with pytest.raises(TypeError, match="float in \\[-1, 1\\] or int16"):
        AudioClip(np.zeros(100, np.int32), RATE)
    with pytest.raises(ValueError, match="positive integer"):
        AudioClip(tone(), -5)
    with pytest.raises(ValueError, match="timeline must be one of"):
        AudioClip(tone(), RATE, timeline="folded")
    with pytest.raises(TypeError, match="file path, or a numpy signal"):
        AudioClip([0.0, 0.1], RATE)


def test_audio_clip_from_a_wav_file(tmp_path):
    path = tmp_path / "beep.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes((tone(1.0, rate=16000) * 32767).astype("<i2").tobytes())
    clip = AudioClip(path)
    assert clip.sample_rate == 16000 and clip.duration == pytest.approx(1.0)
    assert repr(clip).startswith("AudioClip(beep.wav") and clip.metadata()["path"] == str(path)
    resampled = AudioClip(path, sample_rate=RATE, start=0.25, duration=0.5)
    assert resampled.sample_rate == RATE and len(resampled) == 4000


def test_peaks_follow_the_envelope_at_any_zoom():
    t = np.arange(3 * RATE) / RATE
    clip = AudioClip(np.where(t < 1, 0.8, np.where(t < 2, 0.0, 0.2)).astype(np.float32), RATE)
    np.testing.assert_allclose(clip.peaks(0, 3, 3), [0.8, 0.0, 0.2])  # block peaks (zoomed out)
    np.testing.assert_allclose(clip.peaks(0.5, 0.501, 4), [0.8] * 4)  # samples (zoomed in)
    np.testing.assert_allclose(clip.peaks(2.5, 3.5, 2), [0.2, 0.0])  # after the end: silence


# ---------------------------------------------------------------- pipeline
def test_filters_receive_the_whole_signal_and_the_position():
    pipeline = HeadlessPipeline.from_function(one_sound, cache="graph")
    louder, position = pipeline.headless(AudioClip(tone(2.0), RATE), frame=15, gain=2.0)
    assert louder.shape == (16000,) and louder.max() == pytest.approx(1.0, abs=1e-3)
    assert position[0] == pytest.approx(0.5)  # frame 15 at 30 fps
    timeline = pipeline.timeline
    assert timeline.fps == AUDIO_TIMELINE_FPS and timeline.n_frames == 60 and not timeline.has_video
    assert timeline.label() == "00:00.50 / 00:02.00"  # no frame number for a sound
    assert [type(filt) for filt in pipeline.filters[:2]] == [TimelineClockFilter, AudioClipFilter]
    assert [name for name, _ in timeline.tracks] == ["sound"]


def test_moving_the_playhead_does_not_recompute_the_sound():
    for cache, after_seek in ((True, []), ("graph", ["where"])):
        pipeline = HeadlessPipeline.from_function(one_sound, cache=cache)
        pipeline.inputs = [AudioClip(tone(), RATE)]
        pipeline.run()
        CALLS.clear()
        pipeline.timeline.update(30)
        _, position = pipeline.run()
        assert CALLS == after_seek, cache  # cache=True: nothing; graph: only the context reader
        if cache == "graph":
            assert position[0] == pytest.approx(1.0)
        CALLS.clear()
        pipeline.controls[1].update(0.5)  # the gain slider
        pipeline.run()
        assert CALLS == ["amplify", "where"]


def test_cache_false_warns(caplog):
    pipeline = HeadlessPipeline.from_function(one_sound, cache=False)
    with caplog.at_level("WARNING"):
        pipeline.inputs = [AudioClip(tone(), RATE)]
    assert 'cache="graph"' in caplog.text


def test_two_sounds_share_the_timeline():
    pipeline = HeadlessPipeline.from_function(two_sounds, cache="graph")
    (mixed,) = pipeline.headless(AudioClip(tone(2.0), RATE), AudioClip(tone(3.0, 0.2), RATE), mix=0.0)
    assert mixed.shape == (24000,) and mixed[:16000].max() == pytest.approx(0.5, abs=1e-3)
    timeline = pipeline.timeline
    assert timeline.n_frames == 90 and len(timeline.audio_clips) == 2
    assert [name for name, _ in timeline.tracks] == ["a", "b"]
    assert sum(isinstance(filt, TimelineClockFilter) for filt in pipeline.filters) == 1
    plays = {filt.input_name: filt.plays for filt in pipeline.filters if isinstance(filt, AudioClipFilter)}
    assert plays == {"a": True, "b": False}  # the first clip is the default sound


def test_video_and_sound_on_one_timeline():
    pipeline = HeadlessPipeline.from_function(video_and_sound, cache="graph")
    frames = np.zeros((25, 4, 6, 3), np.float32)
    (out,) = pipeline.headless(Video(frames, fps=25), AudioClip(tone(2.0, rate=2 * RATE), 2 * RATE), frame=10)
    assert out.shape == (4, 6) and out[0, 0] == 2.0  # the sound's metadata reaches the filters
    timeline = pipeline.timeline
    assert timeline.fps == 25 and timeline.n_frames == 50 and timeline.has_video  # the video's rate, the longest
    assert not any(isinstance(filt, TimelineClockFilter) for filt in pipeline.filters)  # the video writes it
    assert [type(source).__name__ for _, source in timeline.tracks] == ["Video", "AudioClip"]


def test_inputs_without_sound_remove_the_timeline():
    pipeline = HeadlessPipeline.from_function(one_sound)
    pipeline.inputs = [AudioClip(tone(), RATE)]
    assert pipeline.timeline is not None
    pipeline.inputs = [tone()]
    assert pipeline.timeline is None
    assert not any(isinstance(filt, (TimelineClockFilter, AudioClipFilter)) for filt in pipeline.filters)
    pipeline.inputs = [Video(np.zeros((4, 2, 2), np.float32))]  # a sound becomes a video
    assert isinstance(pipeline.filters[0], VideoFrameFilter)


# ---------------------------------------------------------------- playback
def _record_audio(pipeline):
    requests = []
    bindings = pipeline.framework_state.audio
    bindings.accepts_signals = True
    bindings.load_audio = requests.append
    return requests


@interactive()
def louder_sound(signal):
    audio.set(signal * 2, RATE)
    return signal


def sound_set_by_a_filter(sound):
    out = louder_sound(sound)
    return out


def test_the_first_clip_plays_unless_a_filter_sets_the_sound():
    pipeline = HeadlessPipeline.from_function(one_sound, cache="graph")
    requests = _record_audio(pipeline)
    pipeline.headless(AudioClip(tone(), RATE))
    assert len(requests) == 1 and isinstance(requests[0], AudioRequest)
    assert requests[0].keep_position and requests[0].sample_rate == RATE

    pipeline = HeadlessPipeline.from_function(sound_set_by_a_filter, cache="graph")
    requests = _record_audio(pipeline)
    pipeline.headless(AudioClip(tone(), RATE))
    assert len(requests) == 2 and requests[-1].signal.max() == pytest.approx(1.0, abs=1e-3)  # the filter's last

    pipeline = HeadlessPipeline.from_function(one_sound, cache="graph")
    requests = _record_audio(pipeline)
    pipeline.headless(AudioClip(tone(), RATE, play=False))
    assert requests == []


def test_mixer_seek():
    mixer = SignalMixer(1000, 1, crossfade_ms=10, ramp_ms=1)
    mixer.set(np.linspace(0, 1, 2000, dtype=np.float32), 1000)
    mixer.seek(1.5)
    assert mixer.position_seconds == 1.5  # silent: moved at once
    mixer.play()
    mixer.render(100)
    mixer.seek(0.25)  # audible: cross-faded to the new position
    block = mixer.render(50)
    assert mixer.position_seconds == pytest.approx(0.3)
    assert block[-1, 0] == pytest.approx(0.3 / 2, abs=0.01)  # the ramp from 1.6 s faded out
    mixer.seek(99.0)  # past the end: clamped
    mixer.render(20)
    assert not mixer.playing or mixer.position_seconds <= 2.0


# ---------------------------------------------------------------- GUIs
class FakePlayer:
    """The audio bindings a Qt player registers, recording the timeline's calls."""

    def __init__(self, bindings):
        self.calls = []
        self.clock = 0.0
        self.is_playing = False
        bindings.play = self.play
        bindings.pause = self.pause
        bindings.seek = self.seek
        bindings.position = lambda: self.clock
        bindings.playing = lambda: self.is_playing

    def play(self):
        self.calls.append("play")
        self.is_playing = True

    def pause(self):
        self.calls.append("pause")
        self.is_playing = False

    def seek(self, seconds):
        self.calls.append(("seek", round(seconds, 3)))
        self.clock = seconds


def test_qt_timeline_drives_and_follows_the_sound():
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    pipeline = HeadlessPipeline.from_function(one_sound, cache="graph")
    gui = qt_gui.InteractivePipeQT(pipeline=pipeline, name="sound")
    assert not gui.audio
    qt_gui.QTimer.singleShot(0, gui.close)
    gui(AudioClip(tone(2.0), RATE))
    assert gui.audio  # an AudioClip turns the player on
    widget = gui.window.timeline_widget
    assert not widget.frame_label.isVisible() and widget.fps_label.text() == "8 kHz"
    player = FakePlayer(pipeline.framework_state.audio)
    widget.seek(15)
    assert player.calls == [("seek", 0.5)]
    widget.play()
    assert player.calls[-2:] == [("seek", 0.5), "play"] and pipeline.timeline.playing
    player.clock = 1.2
    widget._tick()  # the playhead follows the sound, without seeking it
    assert pipeline.timeline.value == 36 and player.calls[-1] == "play"
    gui.on_press(" ")
    assert player.calls[-1] == "pause" and not pipeline.timeline.playing
    widget.step(1)
    assert player.calls[-2:] == ["pause", ("seek", round(37 / 30, 3))]
    player.is_playing = True  # a filter called audio.play(): the playhead follows
    widget._background_changed()
    assert pipeline.timeline.playing and widget.play_button.kind == "pause"
    player.is_playing = False  # the sound reached its end: the timer loops, the sound starts over
    pipeline.timeline.value = pipeline.timeline.n_frames - 1
    widget._tick()
    assert pipeline.timeline.value == 0 and player.calls[-2:] == [("seek", 0.0), "play"]
    widget.strip.resize(400, widget.strip.height())
    assert not widget.strip.grab().isNull()  # paints the waveform lane


def test_waveform_lane():
    from interactive_pipe.graphical.timeline_view import DARK, StripView

    class Strip(StripView):
        def strip_width(self):
            return 300

    pipeline = HeadlessPipeline.from_function(two_sounds)
    t = np.arange(2 * RATE) / RATE
    loud_then_quiet = np.where(t < 1, 0.9, 0.05).astype(np.float32)
    pipeline.inputs = [AudioClip(loud_then_quiet, RATE), AudioClip(tone(1.0), RATE)]
    strip = Strip()
    strip.init_strip_view(pipeline.timeline)
    image = strip.strip_image(20)
    lane_a, lane_b = image[:20], image[20 + 3 :]
    painted = (lane_a == DARK.waveform).all(axis=-1).sum(axis=0)
    assert painted[50] > 4 * painted[250] > 0  # loud, then a thin quiet line
    assert (lane_b[:, 200:] == DARK.track_background).all()  # b lasts 1 s of 2: its lane ends
    assert strip.tick_step() in (0.1, 0.2, 0.5, 1)  # round durations, not 30 fps frame multiples


def test_dpg_timeline_with_sounds_only():
    dpg_gui = pytest.importorskip("interactive_pipe.graphical.dpg_gui")
    from interactive_pipe.graphical.timeline_view import strip_height

    pipeline = HeadlessPipeline.from_function(two_sounds, cache="graph")
    gui = dpg_gui.InteractivePipeDPG(pipeline=pipeline, name="sounds dpg")
    gui.run = lambda: None  # no viewport in tests
    gui(AudioClip(tone(), RATE), AudioClip(tone(1.0), RATE))
    panel = gui.window.timeline_panel
    assert gui.audio and panel.n_lanes == 2 and panel.strip_height() == strip_height(2)
    panel.draw()  # waveforms, kHz label
    gui.on_press(" ")
    assert pipeline.timeline.playing
    gui.close()


@pytest.mark.parametrize("backend", ["mpl", "gradio"])
def test_other_backends_show_a_slider_and_turn_audio_on(backend):
    from interactive_pipe.helper.choose_backend import get_interactive_pipeline_class

    try:
        gui_class = get_interactive_pipeline_class(backend)
    except Exception as exc:  # noqa: BLE001 - backend not installed
        pytest.skip(f"{backend}: {exc}")
    pipeline = HeadlessPipeline.from_function(one_sound, cache="graph")
    gui = gui_class(pipeline=pipeline, name="sound")
    gui.run = lambda: None
    gui(AudioClip(tone(), RATE))
    assert gui.audio and any(ctrl is pipeline.timeline for ctrl in gui.controls)
    if backend == "gradio":
        assert gui.window.audio  # the window was built again with its audio player
