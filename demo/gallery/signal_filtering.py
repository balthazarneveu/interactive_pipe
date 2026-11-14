"""1D signal processing: low-pass filtering a noisy chirp with an FIR or an IIR filter.

What to look at: the chirp sweeps from 2 Hz to 60 Hz, so time is frequency here: the filtered
signal fades out where the chirp crosses the cutoff. Compare the FIR (linear phase: a constant delay
of (taps-1)/2 samples, a phase linear in frequency) with the Butterworth IIR (a sharp roll-off from a few
coefficients, but a curved phase, so a frequency-dependent delay). The Bode plot shows magnitude and phase on twin axes.
"""

import numpy as np
from matplotlib.figure import Figure

from interactive_pipe import Control, Curve, SingleCurve, interactive, interactive_pipeline

FS = 500.0  # sampling rate, Hz
CUTOFF = Control(25.0, [2.0, 100.0], name="cutoff (Hz)")  # one slider for design and bode


@interactive(noise=(0.3, [0.0, 1.0]))
def chirp(noise=0.3):
    t = np.arange(0, 4.0, 1 / FS)
    clean = np.sin(2 * np.pi * (2 * t + 29 / 4 * t**2))  # 2 Hz -> 60 Hz in 4 s
    noisy = clean + noise * np.random.default_rng(0).standard_normal(t.size)
    return t, noisy, clean


@interactive(
    kind=("FIR", ["FIR", "IIR"]),
    cutoff=CUTOFF,
    taps=(41, [3, 201], "FIR taps"),
    iir_order=(4, [1, 8], "IIR order"),
)
def design(kind="FIR", cutoff=25.0, taps=41, iir_order=4):
    """Return (b, a): a Hamming windowed-sinc FIR, or a Butterworth IIR (bilinear transform)."""
    if kind == "FIR":
        n = np.arange(taps) - (taps - 1) / 2
        b = np.sinc(2 * cutoff / FS * n) * np.hamming(taps)
        return b / b.sum(), np.array([1.0])
    k = np.arange(1, iir_order + 1)
    poles = 2 * FS * np.tan(np.pi * cutoff / FS) * np.exp(1j * np.pi * (2 * k + iir_order - 1) / (2 * iir_order))
    a = np.real(np.poly((1 + poles / (2 * FS)) / (1 - poles / (2 * FS))))
    b = np.poly(-np.ones(iir_order))
    return b * a.sum() / b.sum(), a


@interactive()
def apply_filter(x, b, a):
    """Direct-form difference equation (numpy only, no scipy)."""
    fir = np.convolve(x, b)[: x.size]
    y = np.zeros(a.size - 1 + x.size)  # leading zeros: past outputs before t=0
    for n in range(x.size):
        y[n + a.size - 1] = fir[n] - np.dot(a[:0:-1], y[n : n + a.size - 1])
    return y[a.size - 1 :]


@interactive()
def plot_signals(t, noisy, filtered, clean):
    return Curve(
        [
            SingleCurve(t, noisy, style="c-", label="noisy", linewidth=1, alpha=0.4),
            SingleCurve(t, clean, style="k-", label="clean", linewidth=1),
            SingleCurve(t, filtered, style="r-", label="filtered", linewidth=2),
        ],
        xlabel="time (s)  ~  chirp frequency 2 Hz -> 60 Hz",
        ylim=(-2.5, 2.5),
        grid=True,
    )


@interactive(cutoff=CUTOFF)
def bode(b, a, cutoff=25.0):
    n = 4096
    f = np.fft.rfftfreq(n, 1 / FS)
    h = np.fft.rfft(b, n) / np.fft.rfft(a, n)
    fig = Figure(figsize=(5, 3.5))
    ax = fig.subplots()
    ax.semilogx(f[1:], 20 * np.log10(np.abs(h[1:]) + 1e-12), "b")
    ax.set(xlabel="frequency (Hz)", ylabel="magnitude (dB)", ylim=(-80, 5))
    ax.grid(True, which="both", alpha=0.3)
    ax.axvline(cutoff, color="gray", linestyle=":")
    twin = ax.twinx()
    twin.semilogx(f[1:], np.degrees(np.unwrap(np.angle(h[1:]))), "r")
    twin.set_ylabel("phase (deg)", color="r")
    fig.tight_layout()
    return fig


@interactive_pipeline(gui="auto")
def signal_filtering():
    t, noisy, clean = chirp()
    b, a = design()
    filtered = apply_filter(noisy, b, a)
    signals = plot_signals(t, noisy, filtered, clean)
    response = bode(b, a)
    return signals, response


if __name__ == "__main__":
    signal_filtering()
