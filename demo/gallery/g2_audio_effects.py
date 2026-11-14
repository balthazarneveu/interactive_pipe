"""Audio: a synthetic A major chord through a guitar-pedal chain (distortion, low-pass, delay).

What to look at: the drive saturates the waveform (flat tops) and adds harmonics, visible as new
horizontal lines in the spectrogram and new peaks in the spectrum; the low-pass cutoff removes
them again. The delay repeats the attack every "delay" ms (vertical stripes in the spectrogram,
decaying with the feedback). In the Qt window the result is played after every change.
"""

import tempfile
import wave
from pathlib import Path
from typing import Annotated

import numpy as np

from interactive_pipe import Curve, audio, interactive, interactive_pipeline, layout

RATE = 16000


def make_chord(seconds=1.5):
    t = np.arange(int(seconds * RATE)) / RATE
    notes = (220.0, 277.18, 329.63)  # A3, C#4, E4
    chord = sum(np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t) for f in notes)
    return 0.25 * chord * np.exp(-5 * t) * np.minimum(t / 0.01, 1)  # pluck: fast attack, slow decay


def write_wav(signal, path=Path(tempfile.gettempdir()) / "g2_audio_effects.wav"):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes((np.clip(signal, -1, 1) * 32767).astype("<i2").tobytes())
    return str(path)


@interactive
def low_pass(signal, cutoff: Annotated[float, (100.0, 8000.0), "cutoff (Hz)"] = 3000.0):
    alpha = 1 - np.exp(-2 * np.pi * cutoff / RATE)  # one-pole filter, twice for 12 dB / octave
    out = signal.copy()
    for _ in range(2):
        acc = 0.0
        for i, x in enumerate(out):
            acc += alpha * (x - acc)
            out[i] = acc
    return out


@interactive
def distortion(signal, drive: Annotated[float, (1.0, 30.0), "drive"] = 3.0):
    return np.tanh(drive * signal) / np.tanh(drive)


@interactive
def delay(
    signal,
    delay_ms: Annotated[float, (20.0, 400.0), "delay (ms)"] = 250.0,
    feedback: Annotated[float, (0.0, 0.9), "feedback"] = 0.4,
    mix: Annotated[float, (0.0, 1.0), "mix"] = 0.5,
):
    d = int(delay_ms * RATE / 1000)
    dry = np.pad(signal, (0, 3 * d))
    wet = np.zeros_like(dry)
    for i in range(d, len(wet)):  # echo: y[n] = x[n - d] + feedback * y[n - d]
        wet[i] = dry[i - d] + feedback * wet[i - d]
    out = (1 - mix) * dry + mix * wet
    out /= max(1.0, np.abs(out).max())
    audio.set(write_wav(out))  # the audio proxy plays a file, not an array
    audio.play()
    return out


@interactive
def analyse(signal):
    t = np.arange(len(signal)) / RATE * 1000
    window = slice(int(0.1 * RATE), int(0.13 * RATE))
    waveform = Curve([[t[window], signal[window], "b-", "output"]], xlabel="time (ms)", ylim=(-1.05, 1.05))
    frames = np.lib.stride_tricks.sliding_window_view(signal, 512)[::128] * np.hanning(512)
    spec = np.abs(np.fft.rfft(frames, axis=-1)).T[:97][::-1]  # 0-3 kHz, low frequencies at the bottom
    spec_db = 20 * np.log10(spec / spec.max() + 1e-6)
    title = "spectrogram: 0-3 kHz (bottom to top), time (left to right)"
    layout.style("spectrogram", title=title, colormap="magma", vmin=-60, vmax=0, colorbar="dB")
    freqs = np.fft.rfftfreq(len(signal), 1 / RATE)
    spectrum = np.abs(np.fft.rfft(signal))
    spectrum = 20 * np.log10(spectrum / spectrum.max() + 1e-6)
    keep = freqs < 3000
    return waveform, spec_db, Curve([[freqs[keep], spectrum[keep], "k-", "spectrum"]], xlabel="Hz", ylabel="dB")


@interactive_pipeline(gui="auto")
def g2_audio_effects(chord):
    driven = distortion(chord)
    toned = low_pass(driven)
    output = delay(toned)
    waveform, spectrogram, spectrum = analyse(output)
    return [[waveform, spectrum], [spectrogram]]


if __name__ == "__main__":
    g2_audio_effects(make_chord())
