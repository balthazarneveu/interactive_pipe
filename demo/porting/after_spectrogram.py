"""Spectrogram with window parameters as controls (port of before_spectrogram.py)."""

from typing import Any, List, Tuple

import numpy as np

from interactive_pipe import Curve, interactive, interactive_pipeline, layout

FS = 8000
DURATION = 1.0


def stft(x: np.ndarray, window: int, hop: int, kind: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    win = np.hanning(window) if kind == "hann" else np.ones(window)
    frames = [x[i : i + window] * win for i in range(0, len(x) - window, hop)]
    spec = np.abs(np.fft.rfft(np.array(frames), axis=1)).T
    freqs = np.fft.rfftfreq(window, 1 / FS)
    times = np.arange(spec.shape[1]) * hop / FS
    return spec, freqs, times


@interactive()
def waveform(signal: np.ndarray) -> Curve:
    t = np.arange(800) / FS
    return Curve([[t, signal[:800], "b-", "signal"]], xlabel="time [s]", title="signal (first 100 ms)")


@interactive(window=(256, [32, 1024]), hop=(64, [8, 256]), window_type=("hann", ["hann", "rect"]))
def spectrogram(signal: np.ndarray, window: int = 256, hop: int = 64, window_type: str = "hann") -> np.ndarray:
    spec, freqs, times = stft(signal, window, hop, window_type)
    db = 20 * np.log10(spec + 1e-6)
    layout.style(
        "db",
        colormap="magma",
        colorbar=True,
        unit="dB",
        extent=(times[0], times[-1], freqs[0], freqs[-1]),
        xlabel="time [s]",
        ylabel="frequency [Hz]",
        title=f"window={window} hop={hop} {window_type}",
    )
    return db[::-1]  # low frequencies at the bottom (imshow origin="lower")


@interactive_pipeline(gui="auto")
def analysis(signal: np.ndarray) -> List[List[Any]]:
    wave = waveform(signal)
    db = spectrogram(signal)
    return [[wave], [db]]


def chirp() -> np.ndarray:
    t = np.arange(int(FS * DURATION)) / FS
    signal = np.sin(2 * np.pi * (200 + 1500 * t) * t) + 0.5 * np.sin(2 * np.pi * 1000 * t)
    return signal + 0.1 * np.random.default_rng(1).normal(size=t.shape)


if __name__ == "__main__":
    analysis(chirp())
