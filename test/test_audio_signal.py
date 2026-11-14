"""audio.set(signal, sample_rate) next to audio.set(path)."""

import os
import wave

import numpy as np
import pytest

from interactive_pipe import audio, interactive
from interactive_pipe.core import context as context_module
from interactive_pipe.headless.pipeline import HeadlessPipeline

RATE = 8000
TONE = np.sin(2 * np.pi * 440 * np.arange(800) / RATE)


def _pipeline(signal_factory, sample_rate=RATE):
    @interactive()
    def sound(gain=0.5):
        signal = signal_factory(gain)
        if sample_rate is None:
            audio.set(signal)
        else:
            audio.set(signal, sample_rate)
        audio.play()
        return signal

    def pipe():
        out = sound()
        return out

    return HeadlessPipeline.from_function(pipe, cache=False)


class Player:
    def __init__(self, pipe):
        self.calls = []
        bindings = pipe.framework_state.audio
        bindings.set_audio = lambda path: self.calls.append(("set", path, _read_wav(path)))
        bindings.play = lambda: self.calls.append(("play",))


def _read_wav(path):
    path = str(path)
    if not path.endswith(".wav") or not os.path.exists(path):
        return None
    with wave.open(path, "rb") as wav:
        frames = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
        return wav.getnchannels(), wav.getframerate(), frames.reshape(-1, wav.getnchannels())


def test_mono_float_signal_is_written_as_16_bit_wav():
    pipe = _pipeline(lambda gain: gain * TONE)
    player = Player(pipe)
    pipe()
    (kind, path, (channels, rate, frames)), play = player.calls
    assert kind == "set" and play == ("play",)
    assert (channels, rate) == (1, RATE)
    np.testing.assert_allclose(frames[:, 0] / 32767, 0.5 * TONE, atol=1e-4)


def test_stereo_and_int16_and_clipping():
    stereo = np.stack([TONE, -TONE], axis=1)
    pipe = _pipeline(lambda gain: (stereo * 1000).astype(np.int16))
    player = Player(pipe)
    pipe()
    channels, rate, frames = player.calls[0][2]
    assert channels == 2
    np.testing.assert_array_equal(frames, (stereo * 1000).astype(np.int16))

    loud = _pipeline(lambda gain: 3.0 * TONE)
    player = Player(loud)
    loud()
    assert player.calls[0][2][2].max() == 32767


def test_previous_file_is_removed_when_the_sound_changes():
    pipe = _pipeline(lambda gain: gain * TONE)
    player = Player(pipe)
    pipe()
    first = player.calls[0][1]
    assert os.path.exists(first)
    pipe.parameters = {"sound": {"gain": 0.2}}
    pipe()
    second = player.calls[2][1]
    assert second != first  # a new name: players cache what a path held
    assert not os.path.exists(first) and os.path.exists(second)
    context_module._remove_temporary_wavs()
    assert not os.path.exists(second)


def test_path_form_is_passed_through(tmp_path):
    wav_path = tmp_path / "x.wav"
    pipe = _pipeline(lambda gain: str(wav_path), sample_rate=None)
    player = Player(pipe)
    pipe()
    assert player.calls[0][1] == str(wav_path)


def test_headless_run_writes_no_file_and_touches_no_device(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("no temporary file without a player")

    monkeypatch.setattr(context_module.tempfile, "mkstemp", forbidden)
    pipe = _pipeline(lambda gain: gain * TONE)
    out = pipe()
    np.testing.assert_allclose(np.asarray(out).ravel(), 0.5 * TONE)
    pipe.snapshot(None)


@pytest.mark.parametrize(
    "signal, rate, match",
    [
        (TONE, None, "integer rate"),
        (TONE, 8000.0, "integer rate"),
        (list(TONE), RATE, "got list"),
        (np.zeros((2, 100)), RATE, r"signal\.T"),
        (np.zeros((10, 3)), RATE, "shape"),
        ("file.wav", RATE, "own sample rate"),
        (np.zeros(10, dtype=complex), RATE, "dtype"),
    ],
)
def test_wrong_calls_show_both_forms(signal, rate, match):
    from interactive_pipe import FilterError

    pipe = _pipeline(lambda gain: signal, sample_rate=rate)
    with pytest.raises(FilterError) as exc_info:
        pipe()
    error = exc_info.value.original_error
    assert isinstance(error, TypeError)
    assert "audio.set(path)" in str(error) and "audio.set(signal, sample_rate)" in str(error)
    assert pytest.importorskip("re").search(match, str(error))
