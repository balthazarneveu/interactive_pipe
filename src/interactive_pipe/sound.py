"""Small audio toolbox for interactive pipelines: load, analyse, denoise, pitch-shift.

Dependency-free (numpy and the standard library; ``ffmpeg`` is used only to
decode compressed files such as ``.mp3`` / ``.mp4`` when it is installed).
Meant to be called inside filters, next to the ``audio`` proxy that plays
the result::

    from interactive_pipe import audio, interactive, layout, sound

    @interactive(semitones=(0.0, [-12.0, 12.0]))
    def shift(signal, semitones=0.0):
        out = sound.pitch_shift(signal, semitones)
        audio.set(out, 16000)
        audio.play()
        return out

    @interactive()
    def show(signal):
        layout.style("spec", **sound.spectrogram_style(signal, 16000))
        return sound.spectrogram(signal)

Conventions shared by every function:

- **Signals** are 1D float arrays in ``[-1, 1]`` (mono). ``load`` returns
  mono by default; the processing functions take mono only.
- **Pure**: the input is never modified; a new ``float32`` array is returned,
  of the same length unless the function says otherwise.
- **STFT** frames use a Hann window, ``n_fft`` samples, ``hop`` samples
  apart (default ``n_fft // 4``), and reconstruct exactly
  (``istft(stft(x)) == x`` up to float error).
"""

import os
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np

__all__ = [
    "load",
    "to_mono",
    "normalize",
    "resample",
    "stft",
    "istft",
    "spectrogram",
    "spectrogram_style",
    "add_noise",
    "snr_db",
    "denoise",
    "time_stretch",
    "pitch_shift",
]

PathLike = Union[str, Path]


# ---------------------------------------------------------------- input / output


def load(
    path: PathLike,
    sample_rate: Optional[int] = None,
    mono: bool = True,
    start: float = 0.0,
    duration: Optional[float] = None,
) -> Tuple[np.ndarray, int]:
    """Read an audio file as ``(signal, sample_rate)``, float32 in ``[-1, 1]``.

    WAV files (8, 16, 24 or 32-bit PCM) are read with the standard library;
    any other format (``.mp3``, ``.mp4``, ``.flac``, ``.ogg``...) is decoded
    with ``ffmpeg`` when it is on the ``PATH``.

    Args:
        path: The file.
        sample_rate: Resample to this rate (Hz); ``None`` keeps the file's.
        mono: Average the channels (shape ``(n,)``); ``False`` keeps
            ``(n, channels)`` for multichannel files.
        start: Skip this many seconds.
        duration: Keep at most this many seconds; ``None`` keeps the rest.

    Raises:
        FileNotFoundError: The file does not exist.
        RuntimeError: Not a WAV file and ``ffmpeg`` is not installed, or ffmpeg failed.
        ValueError: Unsupported WAV sample width.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"sound.load: no such file {path}")
    if path.suffix.lower() == ".wav":
        try:
            signal, rate = _read_wav(path)
        except wave.Error:
            # float / extensible WAV: the wave module reads integer PCM only
            signal, rate = _read_with_ffmpeg(path)
    else:
        signal, rate = _read_with_ffmpeg(path)
    first = int(round(max(start, 0.0) * rate))
    last = None if duration is None else first + int(round(duration * rate))
    signal = signal[first:last]
    if mono:
        signal = to_mono(signal)
    if sample_rate is not None and sample_rate != rate:
        if signal.ndim == 2:  # mono=False: each channel on its own (resample mixes down)
            signal = np.stack([resample(signal[:, ch], rate, sample_rate) for ch in range(signal.shape[1])], axis=1)
        else:
            signal = resample(signal, rate, sample_rate)
        rate = sample_rate
    return signal.astype(np.float32), int(rate)


def _read_wav(path: Path) -> Tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav:
        channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
        raw = wav.readframes(wav.getnframes())
    if width == 1:
        data = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        data = np.frombuffer(raw, "<i2").astype(np.float32) / 32768.0
    elif width == 3:
        bytes3 = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        ints = bytes3[:, 0] | (bytes3[:, 1] << 8) | (bytes3[:, 2] << 16)
        ints = np.where(ints >= 1 << 23, ints - (1 << 24), ints)
        data = ints.astype(np.float32) / float(1 << 23)
    elif width == 4:
        data = np.frombuffer(raw, "<i4").astype(np.float32) / float(1 << 31)
    else:
        raise ValueError(f"sound.load: unsupported WAV sample width {width} bytes in {path}")
    data = data.reshape(-1, channels)
    return (data[:, 0] if channels == 1 else data), rate


_PROBE_TIMEOUT = 30.0  # seconds
_DECODE_TIMEOUT = 300.0


def _read_with_ffmpeg(path: Path) -> Tuple[np.ndarray, int]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError(
            f"sound.load: {path.suffix} files need ffmpeg (not found on the PATH); install it or convert to .wav"
        )
    # absolute: a name starting with "-" is not read as an option, "x:y" not as a protocol
    source = os.path.abspath(path)
    rate = 44100
    probe = shutil.which("ffprobe")
    if probe is not None:
        try:
            found = subprocess.run(
                [probe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate"]
                + ["-of", "csv=p=0", "-i", source],
                capture_output=True,
                text=True,
                timeout=_PROBE_TIMEOUT,
            ).stdout.strip()
        except subprocess.TimeoutExpired:
            found = ""
        if found.isdigit():
            rate = int(found)
    try:
        result = subprocess.run(
            [ffmpeg, "-nostdin", "-v", "error", "-i", source, "-vn", "-f", "f32le", "-acodec", "pcm_f32le"]
            + ["-ar", str(rate), "-ac", "1", "-"],
            capture_output=True,
            timeout=_DECODE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"sound.load: ffmpeg did not finish decoding {path} within {_DECODE_TIMEOUT:.0f} s"
        ) from None
    if result.returncode != 0:
        raise RuntimeError(f"sound.load: ffmpeg could not decode {path}: {result.stderr.decode(errors='replace')}")
    return np.frombuffer(result.stdout, "<f4").copy(), rate


def to_mono(signal: np.ndarray) -> np.ndarray:
    """Average the channels of a ``(n, channels)`` signal; a 1D signal is returned as float32."""
    signal = np.asarray(signal, dtype=np.float32)
    return signal.mean(axis=1) if signal.ndim == 2 else signal


def normalize(signal: np.ndarray, peak: float = 0.9) -> np.ndarray:
    """Scale so that the largest absolute value is ``peak`` (a silent signal is returned unchanged)."""
    signal = np.asarray(signal, dtype=np.float32)
    largest = float(np.max(np.abs(signal))) if signal.size else 0.0
    return signal * (peak / largest) if largest > 0 else signal.copy()


def resample(signal: np.ndarray, rate_in: float, rate_out: float) -> np.ndarray:
    """Change the sampling rate (band-limited, by zero-padding or cropping the spectrum)."""
    signal = to_mono(signal)
    length = int(round(len(signal) * rate_out / rate_in))
    return _resample_to_length(signal, length)


def _resample_to_length(signal: np.ndarray, length: int) -> np.ndarray:
    if length == len(signal) or len(signal) == 0:
        return signal.astype(np.float32).copy()
    spectrum = np.fft.rfft(signal)
    bins = length // 2 + 1
    if bins <= len(spectrum):
        spectrum = spectrum[:bins]
    else:
        spectrum = np.concatenate([spectrum, np.zeros(bins - len(spectrum), dtype=spectrum.dtype)])
    return (np.fft.irfft(spectrum, n=length) * (length / len(signal))).astype(np.float32)


# ---------------------------------------------------------------- short-time Fourier transform


def _hop(n_fft: int, hop: Optional[int]) -> int:
    if n_fft < 4 or n_fft & (n_fft - 1):
        raise ValueError(f"n_fft must be a power of two >= 4, got {n_fft}")
    hop = n_fft // 4 if hop is None else int(hop)
    if not 0 < hop <= n_fft // 2:
        raise ValueError(f"hop must be in [1, n_fft // 2 = {n_fft // 2}], got {hop}")
    return hop


def stft(signal: np.ndarray, n_fft: int = 1024, hop: Optional[int] = None) -> np.ndarray:
    """Complex STFT, shape ``(frames, n_fft // 2 + 1)`` (one row per frame, low frequencies first).

    The signal is padded by ``n_fft // 2`` on both sides so that frame ``i``
    is centred on sample ``i * hop``.
    """
    hop = _hop(n_fft, hop)
    signal = to_mono(signal)
    if signal.ndim != 1:
        raise ValueError(f"stft expects a 1D signal, got shape {signal.shape}")
    pad = n_fft // 2
    padded = np.pad(signal, (pad, pad + n_fft))
    frames = 1 + (len(signal) + pad * 2 - n_fft) // hop + 1
    index = np.arange(n_fft)[None, :] + hop * np.arange(frames)[:, None]
    return np.fft.rfft(padded[index] * np.hanning(n_fft + 1)[:-1], axis=1)


def istft(spectrum: np.ndarray, hop: Optional[int] = None, length: Optional[int] = None) -> np.ndarray:
    """Inverse of :func:`stft` (weighted overlap-add); ``length`` crops to the original signal length."""
    n_fft = 2 * (spectrum.shape[1] - 1)
    hop = _hop(n_fft, hop)
    window = np.hanning(n_fft + 1)[:-1]
    frames = np.fft.irfft(spectrum, n=n_fft, axis=1) * window
    total = n_fft + hop * (len(frames) - 1)
    out = np.zeros(total)
    norm = np.zeros(total)
    for i, frame in enumerate(frames):
        out[i * hop : i * hop + n_fft] += frame
        norm[i * hop : i * hop + n_fft] += window**2
    out = out / np.maximum(norm, 1e-8)
    pad = n_fft // 2
    out = out[pad:]
    if length is not None:
        out = out[:length]
        if len(out) < length:
            out = np.pad(out, (0, length - len(out)))
    return out.astype(np.float32)


def spectrogram(
    signal: np.ndarray,
    n_fft: int = 512,
    hop: Optional[int] = None,
    floor_db: float = -80.0,
) -> np.ndarray:
    """Log-magnitude spectrogram in dB, ready to display as a heatmap.

    Shape ``(n_fft // 2 + 1, frames)``: time runs left to right and **low
    frequencies are at the bottom** (row 0 is the Nyquist frequency), as on
    any spectrogram plot. 0 dB is a full-scale sine; values below
    ``floor_db`` are clipped. Pair it with :func:`spectrogram_style` for the
    colormap and the time / frequency axes.
    """
    spectrum = stft(signal, n_fft, hop)
    magnitude = np.abs(spectrum) / (np.hanning(n_fft + 1)[:-1].sum() / 2)
    decibels = 20 * np.log10(np.maximum(magnitude, 1e-10))
    return np.clip(decibels, floor_db, 0.0).T[::-1].astype(np.float32)


def spectrogram_style(
    signal: np.ndarray,
    sample_rate: int,
    floor_db: float = -80.0,
    colormap: str = "magma",
    title: Optional[str] = None,
) -> Dict[str, Any]:
    """Keyword arguments for ``layout.style(name, **...)`` matching :func:`spectrogram`.

    Time axis in seconds, frequency axis in kHz, a dB colour bar.
    """
    style = dict(
        colormap=colormap,
        vmin=floor_db,
        vmax=0.0,
        colorbar=True,
        unit="dB",
        extent=(0.0, len(signal) / sample_rate, 0.0, sample_rate / 2000.0),
        xlabel="time [s]",
        ylabel="frequency [kHz]",
    )
    if title is not None:
        style["title"] = title
    return style


# ---------------------------------------------------------------- noise


def add_noise(
    signal: np.ndarray,
    snr: float = 10.0,
    kind: str = "white",
    sample_rate: int = 16000,
    seed: int = 0,
) -> Tuple[np.ndarray, np.ndarray]:
    """Add noise at a given signal-to-noise ratio (dB); returns ``(noisy, noise)``.

    Kinds: ``"white"`` (flat spectrum), ``"pink"`` (1/f, louder in the
    lows, like wind or a fan), ``"hum"`` (50 Hz mains and its harmonics plus
    a little hiss; uses ``sample_rate``). Deterministic for a given ``seed``.
    """
    signal = to_mono(signal)
    rng = np.random.default_rng(seed)
    n = len(signal)
    if kind == "white":
        noise = rng.standard_normal(n)
    elif kind == "pink":
        spectrum = np.fft.rfft(rng.standard_normal(n))
        spectrum /= np.sqrt(np.maximum(np.arange(len(spectrum)), 1.0))
        noise = np.fft.irfft(spectrum, n=n)
    elif kind == "hum":
        t = np.arange(n) / sample_rate
        noise = sum(np.sin(2 * np.pi * 50 * k * t + k) / k for k in range(1, 8))
        noise = noise + 0.1 * rng.standard_normal(n)
    else:
        raise ValueError(f"add_noise: unknown kind {kind!r}, expected 'white', 'pink' or 'hum'")
    power_signal = float(np.mean(signal**2))
    power_noise = float(np.mean(noise**2))
    if power_signal == 0 or power_noise == 0:
        return signal.copy(), np.zeros_like(signal)
    noise = (noise * np.sqrt(power_signal / power_noise / 10 ** (snr / 10))).astype(np.float32)
    return (signal + noise).astype(np.float32), noise


def snr_db(reference: np.ndarray, estimate: np.ndarray) -> float:
    """Signal-to-noise ratio of ``estimate`` against ``reference`` in dB (``inf`` when identical)."""
    reference, estimate = to_mono(reference), to_mono(estimate)
    error = float(np.sum((reference - estimate) ** 2))
    if error == 0:
        return float("inf")
    return float(10 * np.log10(max(float(np.sum(reference**2)), 1e-20) / error))


def _smooth(values: np.ndarray, size: int, axis: int) -> np.ndarray:
    """Moving average along one axis (edges padded with their own values)."""
    if size <= 1:
        return values
    pad = [(0, 0)] * values.ndim
    pad[axis] = (size // 2, size - 1 - size // 2)
    padded = np.pad(values, pad, mode="edge")
    total = np.cumsum(padded, axis=axis)
    total = np.concatenate([np.zeros_like(np.take(total, [0], axis=axis)), total], axis=axis)
    upper = np.take(total, np.arange(size, total.shape[axis]), axis=axis)
    lower = np.take(total, np.arange(0, total.shape[axis] - size), axis=axis)
    return (upper - lower) / size


def denoise(
    signal: np.ndarray,
    strength: float = 1.5,
    max_attenuation_db: float = 30.0,
    noise: Optional[np.ndarray] = None,
    n_fft: int = 1024,
    smoothing: int = 3,
) -> np.ndarray:
    """Remove stationary noise (hiss, hum, fan) by spectral gating.

    Each time-frequency bin is attenuated by how much of it the noise
    explains: ``gain = 1 - strength * noise_level / level``, limited to
    ``-max_attenuation_db`` and smoothed over ``smoothing`` frames and bins
    (fewer "musical noise" chirps).

    Args:
        signal: The noisy signal.
        strength: Over-subtraction factor: 0 does nothing, 1 subtracts the
            noise estimate, more removes more noise (and more signal).
        max_attenuation_db: Deepest cut in dB; a floor keeps a natural
            residual instead of holes.
        noise: A noise-only recording (any length) to take the noise
            spectrum from. ``None`` estimates it from the signal itself
            (the quietest 10% of each frequency band over time), which
            works when the noise is steady and the signal has pauses.
        n_fft: STFT size; larger resolves hum lines better, smaller smears less in time.
        smoothing: Width (frames and bins) of the gain smoothing, 1 for none.
    """
    signal = to_mono(signal)
    spectrum = stft(signal, n_fft)
    magnitude = np.abs(spectrum)
    if noise is not None:
        noise_level = np.abs(stft(noise, n_fft)).mean(axis=0, keepdims=True)
    else:
        noise_level = np.percentile(magnitude, 10, axis=0, keepdims=True) * 1.5
    floor = 10 ** (-abs(max_attenuation_db) / 20)
    gain = np.clip(1.0 - strength * noise_level / np.maximum(magnitude, 1e-10), floor, 1.0)
    gain = _smooth(_smooth(gain, smoothing, axis=0), smoothing, axis=1)
    return istft(spectrum * gain, length=len(signal))


# ---------------------------------------------------------------- time and pitch


def time_stretch(signal: np.ndarray, factor: float, n_fft: int = 1024) -> np.ndarray:
    """Make the signal ``factor`` times longer without changing its pitch (phase vocoder).

    ``factor=2`` plays twice as slow, ``0.5`` twice as fast; the output has
    about ``factor * len(signal)`` samples.
    """
    if factor <= 0:
        raise ValueError(f"time_stretch: factor must be > 0, got {factor}")
    signal = to_mono(signal)
    hop = n_fft // 4
    spectrum = stft(signal, n_fft, hop)
    if len(spectrum) < 2:
        return signal.copy()
    positions = np.arange(0, len(spectrum) - 1, 1.0 / factor)
    index = positions.astype(int)
    fraction = (positions - index)[:, None]
    magnitude = (1 - fraction) * np.abs(spectrum[index]) + fraction * np.abs(spectrum[index + 1])
    expected = 2 * np.pi * hop * np.arange(spectrum.shape[1]) / n_fft
    deviation = np.angle(spectrum[index + 1]) - np.angle(spectrum[index]) - expected
    deviation -= 2 * np.pi * np.round(deviation / (2 * np.pi))
    phase = np.angle(spectrum[0]) + np.concatenate(
        [np.zeros((1, spectrum.shape[1])), np.cumsum(expected + deviation, axis=0)[:-1]]
    )
    return istft(magnitude * np.exp(1j * phase), hop, length=int(round(len(signal) * factor)))


def pitch_shift(signal: np.ndarray, semitones: float, n_fft: int = 1024) -> np.ndarray:
    """Raise (or lower, negative) the pitch by ``semitones`` keeping the duration.

    Phase-vocoder stretch by ``2 ** (semitones / 12)`` then resampling back
    to the original length. Formants move with the pitch: +12 sounds like a
    chipmunk, -12 like a giant. ``n_fft`` 1024 suits 16-22 kHz audio
    (2048 at 44.1 kHz).
    """
    signal = to_mono(signal)
    if semitones == 0:
        return signal.copy()
    ratio = 2.0 ** (semitones / 12.0)
    stretched = time_stretch(signal, ratio, n_fft)
    return _resample_to_length(stretched, len(signal))
