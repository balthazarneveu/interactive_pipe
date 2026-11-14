"""Spectrogram of a chirp + tone with window parameters."""

import matplotlib.pyplot as plt
import numpy as np

FS = 8000
DURATION = 1.0
WINDOW = 256
HOP = 64
WINDOW_TYPE = "hann"

t = np.arange(int(FS * DURATION)) / FS
signal = np.sin(2 * np.pi * (200 + 1500 * t) * t) + 0.5 * np.sin(2 * np.pi * 1000 * t)
signal += 0.1 * np.random.default_rng(1).normal(size=t.shape)


def stft(x, window, hop, kind):
    win = np.hanning(window) if kind == "hann" else np.ones(window)
    frames = [x[i : i + window] * win for i in range(0, len(x) - window, hop)]
    spec = np.abs(np.fft.rfft(np.array(frames), axis=1)).T
    freqs = np.fft.rfftfreq(window, 1 / FS)
    times = np.arange(spec.shape[1]) * hop / FS
    return spec, freqs, times


spec, freqs, times = stft(signal, WINDOW, HOP, WINDOW_TYPE)
db = 20 * np.log10(spec + 1e-6)

fig, axes = plt.subplots(2, 1, figsize=(8, 6))
axes[0].plot(t[:800], signal[:800])
axes[0].set_title("signal (first 100 ms)")
axes[1].imshow(db, origin="lower", aspect="auto", extent=(times[0], times[-1], freqs[0], freqs[-1]), cmap="magma")
axes[1].set_xlabel("time [s]")
axes[1].set_ylabel("frequency [Hz]")
axes[1].set_title(f"window={WINDOW} hop={HOP} {WINDOW_TYPE}")
plt.tight_layout()
plt.show()
