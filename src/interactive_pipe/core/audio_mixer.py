"""Sample-accurate playback state for streamed signals (no Qt, no audio device).

The GUI's audio thread asks :meth:`SignalMixer.render` for the next block of
samples; filters replace the signal at any time with :meth:`SignalMixer.set`.
Everything that makes tweaking a sound while listening fluid lives here:

- the playhead is a sample index, so a new version of the sound continues at
  exactly the same instant (``keep_position``);
- a swap cross-fades from the previous signal to the new one over
  ``crossfade_ms`` (both read at their own playhead, so a restart from the
  beginning is click-free too);
- play / pause / stop ramp the gain over ``ramp_ms`` instead of cutting;
- signals are converted to the output's rate and channel count once, when
  set (not in the audio thread).

Thread safety: every public method takes the same lock; ``render`` does a few
numpy slices under it, never I/O.
"""

import threading
from typing import Optional

import numpy as np


def _resample(signal: np.ndarray, rate_in: int, rate_out: int) -> np.ndarray:
    """Band-limited resampling along axis 0 (FFT zero-padding / cropping)."""
    if rate_in == rate_out or len(signal) == 0:
        return signal
    length = max(1, int(round(len(signal) * rate_out / rate_in)))
    spectrum = np.fft.rfft(signal, axis=0)
    bins = length // 2 + 1
    if bins <= spectrum.shape[0]:
        spectrum = spectrum[:bins]
    else:
        spectrum = np.concatenate([spectrum, np.zeros((bins - spectrum.shape[0],) + spectrum.shape[1:])], axis=0)
    return (np.fft.irfft(spectrum, n=length, axis=0) * (length / len(signal))).astype(np.float32)


def _channels(signal: np.ndarray, channels: int) -> np.ndarray:
    if signal.shape[1] == channels:
        return signal
    mono = signal.mean(axis=1, keepdims=True)
    return np.repeat(mono, channels, axis=1)


def to_float_frames(signal: np.ndarray) -> np.ndarray:
    """``(n,)`` or ``(n, channels)``, float in [-1, 1] or int16 -> float32 ``(n, channels)`` clipped to [-1, 1]."""
    if signal.dtype == np.int16:
        frames = signal.astype(np.float32) / 32768.0
    else:
        frames = np.nan_to_num(signal.astype(np.float32, copy=False))
    if frames.ndim == 1:
        frames = frames[:, None]
    return np.clip(frames, -1.0, 1.0)


class _Voice:
    """A signal, its own playhead and its own cross-fade gain."""

    __slots__ = ("frames", "position", "gain", "target")

    def __init__(self, frames: np.ndarray, position: int = 0, gain: float = 1.0, target: float = 1.0):
        self.frames = frames
        self.position = position
        self.gain = gain
        self.target = target

    def read(self, count: int, loop: bool) -> np.ndarray:
        """Next ``count`` frames (zeros after the end unless looping); advances the playhead."""
        total = len(self.frames)
        out = np.zeros((count, self.frames.shape[1]), dtype=np.float32)
        if total == 0:
            return out
        filled = 0
        while filled < count:
            if self.position >= total:
                if not loop:
                    break
                self.position = 0
            take = min(count - filled, total - self.position)
            out[filled : filled + take] = self.frames[self.position : self.position + take]
            filled += take
            self.position += take
        return out

    def finished(self) -> bool:
        return self.position >= len(self.frames)


def _ramp(start: float, target: float, step: float, count: int) -> np.ndarray:
    """``count`` gains going linearly from ``start`` towards ``target`` by ``step`` per frame, then holding."""
    if start == target:
        return np.full(count, start, dtype=np.float32)
    direction = 1.0 if target > start else -1.0
    ramp = start + direction * step * (1 + np.arange(count, dtype=np.float32))
    return np.minimum(ramp, target) if direction > 0 else np.maximum(ramp, target)


class SignalMixer:
    MAX_VOICES = 8  # versions fading out at once; beyond, the quietest is dropped

    def __init__(self, rate: int, channels: int, crossfade_ms: float = 30.0, ramp_ms: float = 8.0):
        self.rate = int(rate)
        self.channels = int(channels)
        self.crossfade_step = 1.0 / max(1, int(self.rate * crossfade_ms / 1000))
        self.ramp_step = 1.0 / max(1, int(self.rate * ramp_ms / 1000))
        self._lock = threading.Lock()
        self._voices: list = []  # the last one is the current sound, the others fade out
        self._loop = False
        self._gain = 0.0  # master gain (play / pause), ramps towards _target
        self._target = 0.0
        self._rewind_when_silent = False  # stop(): back to the start once faded out

    @property
    def _current(self) -> Optional[_Voice]:
        return self._voices[-1] if self._voices else None

    # ------------------------------------------------------------------ control (any thread)

    def set(self, signal: np.ndarray, sample_rate: int, keep_position: bool = True, loop: bool = False) -> None:
        """Replace the signal; ``keep_position`` continues at the same instant."""
        frames = _channels(_resample(to_float_frames(signal), int(sample_rate), self.rate), self.channels)
        with self._lock:
            current = self._current
            position = current.position if keep_position and current is not None else 0
            if position >= len(frames):
                position = 0  # past the end of the new sound: from the beginning
            audible = self._gain > 0 or self._target > 0
            if not audible:
                self._voices = [_Voice(frames, position)]
            else:
                for voice in self._voices:
                    voice.target = 0.0
                # versions never heard (gain still 0) are dropped: no jump, they were silent
                self._voices = [voice for voice in self._voices if voice.gain > 0]
                if len(self._voices) >= self.MAX_VOICES:
                    self._voices.remove(min(self._voices, key=lambda voice: voice.gain))
                self._voices.append(_Voice(frames, position, gain=0.0, target=1.0))
            self._loop = bool(loop)

    def seek(self, seconds: float) -> None:
        """Move the playhead to ``seconds`` (cross-faded while audible, like a new version of the sound)."""
        with self._lock:
            current = self._current
            if current is None:
                return
            position = min(max(int(round(seconds * self.rate)), 0), len(current.frames))
            if self._gain == 0 and self._target == 0:
                current.position = position
                self._voices = [current]
                self._rewind_when_silent = False
                return
            for voice in self._voices:
                voice.target = 0.0
            self._voices = [voice for voice in self._voices if voice.gain > 0]
            if len(self._voices) >= self.MAX_VOICES:
                self._voices.remove(min(self._voices, key=lambda voice: voice.gain))
            self._voices.append(_Voice(current.frames, position, gain=0.0, target=1.0))

    def play(self) -> None:
        with self._lock:
            current = self._current
            if current is not None and current.finished():
                current.position = 0
            self._target = 1.0
            self._rewind_when_silent = False

    def pause(self) -> None:
        with self._lock:
            self._target = 0.0

    def stop(self) -> None:
        with self._lock:
            self._target = 0.0
            self._rewind_when_silent = True

    @property
    def playing(self) -> bool:
        with self._lock:
            return self._target > 0

    @property
    def position_seconds(self) -> float:
        with self._lock:
            current = self._current
            return 0.0 if current is None else current.position / self.rate

    # ------------------------------------------------------------------ audio thread

    def render(self, count: int) -> np.ndarray:
        """The next ``count`` frames, float32 ``(count, channels)``."""
        with self._lock:
            out = np.zeros((count, self.channels), dtype=np.float32)
            current = self._current
            if current is None or (self._gain == 0 and self._target == 0):
                self._settle_silent()
                return out
            for voice in self._voices:
                gains = _ramp(voice.gain, voice.target, self.crossfade_step, count)
                out += voice.read(count, self._loop) * gains[:, None]
                voice.gain = float(gains[-1])
            self._voices = [voice for voice in self._voices if voice is current or voice.gain > 0]
            master = _ramp(self._gain, self._target, self.ramp_step, count)
            self._gain = float(master[-1])
            out *= master[:, None]
            if self._gain == 0 and self._target == 0:
                self._settle_silent()
            elif not self._loop and current.finished() and len(self._voices) == 1:
                self._target = self._gain = 0.0  # played to the end: stopped, next play() restarts
                current.position = 0
            return out

    def _settle_silent(self) -> None:
        """Silent: finish every fade at once, rewind if stop() asked for it."""
        current = self._current
        if current is None:
            return
        current.gain = current.target = 1.0
        self._voices = [current]
        if self._rewind_when_silent:
            current.position = 0
            self._rewind_when_silent = False
