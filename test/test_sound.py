"""interactive_pipe.sound: audio helpers (pure numpy)."""

import shutil
import wave
from pathlib import Path

import numpy as np
import pytest

from interactive_pipe import sound

RATE = 16000
ROOT = Path(__file__).resolve().parent.parent


def sine(frequency=440.0, seconds=1.0, amplitude=0.5, rate=RATE):
    t = np.arange(int(seconds * rate)) / rate
    return (amplitude * np.sin(2 * np.pi * frequency * t)).astype(np.float32)


def peak_frequency(signal, rate=RATE):
    spectrum = np.abs(np.fft.rfft(signal * np.hanning(len(signal))))
    return np.argmax(spectrum) * rate / len(signal)


@pytest.mark.parametrize("length", [100, 1000, 4097])
@pytest.mark.parametrize("n_fft, hop", [(256, None), (1024, 256), (512, 128)])
def test_stft_roundtrip(length, n_fft, hop):
    signal = np.random.default_rng(0).standard_normal(length).astype(np.float32)
    restored = sound.istft(sound.stft(signal, n_fft, hop), hop, length=length)
    assert restored.shape == signal.shape
    np.testing.assert_allclose(restored, signal, atol=1e-5)


def test_stft_rejects_bad_sizes():
    with pytest.raises(ValueError, match="power of two"):
        sound.stft(sine(), n_fft=1000)
    with pytest.raises(ValueError, match="hop"):
        sound.stft(sine(), n_fft=256, hop=200)


def test_input_is_not_modified():
    signal = sine()
    original = signal.copy()
    sound.denoise(signal)
    sound.pitch_shift(signal, 3)
    sound.add_noise(signal)
    np.testing.assert_array_equal(signal, original)


@pytest.mark.parametrize("semitones", [-12, -5, 7, 12])
def test_pitch_shift_moves_the_frequency_and_keeps_the_length(semitones):
    signal = sine(440.0, seconds=1.0)
    shifted = sound.pitch_shift(signal, semitones)
    assert shifted.shape == signal.shape
    assert shifted.dtype == np.float32
    assert peak_frequency(shifted) == pytest.approx(440.0 * 2 ** (semitones / 12), rel=0.01)


def test_pitch_shift_zero_is_identity():
    signal = sine()
    np.testing.assert_array_equal(sound.pitch_shift(signal, 0), signal)


@pytest.mark.parametrize("factor", [0.5, 1.5, 2.0])
def test_time_stretch_changes_the_length_not_the_pitch(factor):
    stretched = sound.time_stretch(sine(440.0), factor)
    assert len(stretched) == int(round(RATE * factor))
    assert peak_frequency(stretched) == pytest.approx(440.0, rel=0.01)
    with pytest.raises(ValueError):
        sound.time_stretch(sine(), 0)


@pytest.mark.parametrize("kind", ["white", "pink", "hum"])
def test_add_noise_reaches_the_requested_snr(kind):
    clean = sine()
    noisy, noise = sound.add_noise(clean, snr=6.0, kind=kind, sample_rate=RATE, seed=3)
    assert sound.snr_db(clean, noisy) == pytest.approx(6.0, abs=0.01)
    np.testing.assert_allclose(noisy - clean, noise, atol=1e-6)
    again, _ = sound.add_noise(clean, snr=6.0, kind=kind, sample_rate=RATE, seed=3)
    np.testing.assert_array_equal(noisy, again)  # deterministic
    with pytest.raises(ValueError, match="unknown kind"):
        sound.add_noise(clean, kind="brown")


def test_snr_of_identical_signals_is_infinite():
    assert sound.snr_db(sine(), sine()) == float("inf")


def bursts(seconds=2.0):
    """Tones with pauses: what a blind noise estimate needs."""
    signal = sine(330.0, seconds) + sine(660.0, seconds, amplitude=0.2)
    t = np.arange(len(signal)) / RATE
    return (signal * ((t % 0.5) < 0.3)).astype(np.float32)


@pytest.mark.parametrize("kind", ["white", "pink", "hum"])
def test_denoise_improves_snr(kind):
    clean = bursts()
    noisy, noise = sound.add_noise(clean, snr=0.0, kind=kind, sample_rate=RATE)
    blind = sound.snr_db(clean, sound.denoise(noisy))
    oracle = sound.snr_db(clean, sound.denoise(noisy, noise=noise))
    assert blind > 5.0
    assert oracle > 5.0


def test_denoise_strength_zero_is_transparent():
    noisy, _ = sound.add_noise(bursts(), snr=0.0)
    np.testing.assert_allclose(sound.denoise(noisy, strength=0.0), noisy, atol=1e-5)


def test_spectrogram_orientation_and_style():
    spec = sound.spectrogram(sine(2000.0), n_fft=512, floor_db=-70)
    assert spec.shape[0] == 257
    assert spec.min() >= -70 and spec.max() <= 0
    row = np.argmax(spec.mean(axis=1))
    frequency = (256 - row) * RATE / 512  # row 0 is Nyquist: low frequencies at the bottom
    assert frequency == pytest.approx(2000.0, abs=RATE / 512)
    assert spec.max() == pytest.approx(-6.0, abs=0.5)  # 0.5 full scale
    style = sound.spectrogram_style(sine(seconds=2.0), RATE, title="t")
    assert style["extent"] == (0.0, 2.0, 0.0, 8.0)
    assert style["title"] == "t"


def test_resample_and_normalize():
    signal = sine(440.0, seconds=1.0, rate=RATE)
    down = sound.resample(signal, RATE, 8000)
    assert len(down) == 8000
    assert peak_frequency(down, 8000) == pytest.approx(440.0, rel=0.01)
    assert np.max(np.abs(sound.normalize(signal, 0.9))) == pytest.approx(0.9)
    np.testing.assert_array_equal(sound.normalize(np.zeros(10)), np.zeros(10))
    assert sound.to_mono(np.ones((5, 2))).shape == (5,)


@pytest.mark.parametrize("width", [1, 2, 3, 4])
def test_load_wav(tmp_path, width):
    signal = sine(440.0, seconds=0.5)
    stereo = np.stack([signal, signal], axis=1)
    scale = 2 ** (8 * width - 1) - 1
    ints = np.round(stereo * scale).astype(np.int64)
    if width == 1:
        raw = (ints + 128).astype(np.uint8).tobytes()
    else:
        raw = b"".join(int(v).to_bytes(width, "little", signed=True) for v in ints.ravel())
    path = tmp_path / "tone.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(width)
        wav.setframerate(RATE)
        wav.writeframes(raw)
    loaded, rate = sound.load(path)
    assert rate == RATE and loaded.dtype == np.float32
    np.testing.assert_allclose(loaded, signal, atol=2.0 / 2 ** (8 * width - 1) + 1e-6)
    both, _ = sound.load(path, mono=False, start=0.1, duration=0.2)
    assert both.shape == (int(0.2 * RATE), 2)
    down, rate = sound.load(path, sample_rate=8000)
    assert rate == 8000 and len(down) == len(signal) // 2


def test_load_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        sound.load(tmp_path / "missing.wav")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_load_compressed_file_with_ffmpeg():
    signal, rate = sound.load(ROOT / "demo" / "audio" / "rabbit.mp4", sample_rate=RATE, duration=1.0)
    assert rate == RATE and signal.shape == (RATE,)
    assert 0.01 < np.sqrt(np.mean(signal**2)) < 1.0


def test_load_compressed_file_without_ffmpeg(monkeypatch, tmp_path):
    path = tmp_path / "clip.mp3"
    path.write_bytes(b"not audio")
    monkeypatch.setattr(sound.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="ffmpeg"):
        sound.load(path)
