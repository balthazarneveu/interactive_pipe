"""SignalMixer: sample-accurate swaps, cross-fades and click-free play / pause / stop."""

import threading

import numpy as np
import pytest

from interactive_pipe.core.audio_mixer import SignalMixer, to_float_frames

RATE = 8000
SECONDS = 2.0
T = np.arange(int(SECONDS * RATE)) / RATE


def tone(amplitude=0.5, frequency=200.0):
    return (amplitude * np.sin(2 * np.pi * frequency * T)).astype(np.float32)


def max_step(signal):
    """Largest second difference: a click shows as a spike far above a smooth tone's."""
    return float(np.abs(np.diff(signal, 2)).max())


SMOOTH = max_step(tone(0.7))  # a clean tone at the largest amplitude used below


def rising_crossings(signal):
    """Indices where the signal goes from negative to non-negative."""
    return np.nonzero((signal[:-1] < 0) & (signal[1:] >= 0))[0]


def render(mixer, total, block=256):
    return np.concatenate([mixer.render(block)[:, 0] for _ in range(total // block)])


def playing(signal=None, loop=True, channels=1, rate=RATE):
    mixer = SignalMixer(rate, channels)
    mixer.set(tone() if signal is None else signal, RATE, keep_position=False, loop=loop)
    mixer.play()
    return mixer


def test_silent_until_played():
    mixer = SignalMixer(RATE, 1)
    assert not mixer.render(100).any()
    mixer.set(tone(), RATE)
    assert not mixer.render(100).any()


def test_plays_the_signal_after_a_short_fade_in():
    mixer = playing()
    out = render(mixer, 4096)
    np.testing.assert_allclose(out[200:], tone()[200:4096], atol=1e-6)
    assert abs(out[0]) < abs(tone()[1]) + 1e-6  # ramped from silence


@pytest.mark.parametrize("swaps_per_block", [1, 3])
def test_swaps_keep_the_position_and_never_click(swaps_per_block):
    mixer = playing()
    rng = np.random.default_rng(0)
    blocks = []
    for _ in range(60):
        for _ in range(swaps_per_block):  # several versions between two audio blocks: a slider drag
            mixer.set(tone(0.3 + 0.4 * rng.random()), RATE, loop=True)
        blocks.append(mixer.render(int(rng.integers(32, 512)))[:, 0])
    out = np.concatenate(blocks)
    assert max_step(out[100:]) < 3 * SMOOTH
    # the playhead never jumped: the phase of the tone is continuous
    periods = np.diff(rising_crossings(out[200:]))
    assert periods.min() >= RATE / 200 - 1 and periods.max() <= RATE / 200 + 1


def test_restart_from_the_beginning_is_cross_faded_too():
    mixer = playing()
    render(mixer, 1000)
    mixer.set(tone(0.5, 330.0), RATE, keep_position=False)
    out = render(mixer, 2048)
    assert max_step(out) < 3 * max_step(tone(0.5, 330.0))
    assert mixer.position_seconds == pytest.approx(2048 / RATE)


def test_kept_position_past_the_end_of_a_shorter_sound_restarts_it():
    mixer = playing()
    render(mixer, 4096)
    mixer.set(tone()[:1000], RATE, loop=True)
    mixer.render(1)
    assert mixer.position_seconds < 1000 / RATE


def test_pause_and_resume_ramp_and_keep_the_position():
    mixer = playing()
    render(mixer, 2048)
    mixer.pause()
    fading = render(mixer, 512)
    assert max_step(fading) < 3 * SMOOTH and not mixer.render(64).any()
    position = mixer.position_seconds
    render(mixer, 1024)
    assert mixer.position_seconds == position  # frozen while paused
    mixer.play()
    assert render(mixer, 512).any() and mixer.position_seconds > position


def test_stop_fades_out_then_rewinds():
    mixer = playing()
    render(mixer, 2048)
    mixer.stop()
    render(mixer, 512)
    assert mixer.position_seconds == 0 and not mixer.playing


def test_without_loop_the_sound_ends_and_play_restarts_it():
    mixer = playing(tone()[:1000], loop=False)
    out = render(mixer, 2048)
    assert out[:1000].any() and not out[1100:].any()
    assert not mixer.playing
    mixer.play()
    assert render(mixer, 256).any()


def test_loop_wraps_without_a_gap():
    mixer = playing()
    out = render(mixer, int(2.5 * len(T)) // 256 * 256)
    assert max_step(out[100:]) < 3 * SMOOTH  # the tone has a whole number of periods: a seamless loop


def test_rate_and_channels_are_converted_when_set():
    mixer = playing(channels=2, rate=2 * RATE)
    out = mixer.render(4096)
    assert out.shape == (4096, 2)
    np.testing.assert_allclose(out[:, 0], out[:, 1])
    crossings = rising_crossings(out[200:, 0])
    assert np.median(np.diff(crossings)) == pytest.approx(2 * RATE / 200, abs=1)


def test_to_float_frames():
    frames = to_float_frames(np.array([0, 16384, -32768], dtype=np.int16))
    np.testing.assert_allclose(frames[:, 0], [0.0, 0.5, -1.0])
    clipped = to_float_frames(np.array([[2.0, np.nan]]))
    np.testing.assert_array_equal(clipped, [[1.0, 0.0]])


def test_concurrent_sets_and_renders():
    mixer = playing()
    errors = []

    def swap():
        try:
            for index in range(200):
                mixer.set(tone(0.3 + 0.001 * index), RATE, loop=True)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    thread = threading.Thread(target=swap)
    thread.start()
    blocks = [mixer.render(128)[:, 0] for _ in range(400)]
    thread.join()
    assert not errors
    assert max_step(np.concatenate(blocks)[100:]) < 3 * SMOOTH
