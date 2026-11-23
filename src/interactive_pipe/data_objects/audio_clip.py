"""``AudioClip``: a sound given as a pipeline input, with a timeline.

Call a pipeline with ``AudioClip("song.wav")`` (or a numpy signal and its
rate): the filters receive the whole signal as a numpy array, the window
shows a timeline with the waveform, and <kbd>Space</kbd> plays / pauses the
sound (Qt) with the playhead following it. See ``headless/timeline.py`` for
how the pipeline installs it and ``docs/guide/audio.md`` for the guide.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np

#: samples per block of the peak envelope (waveform drawing at any zoom)
PEAK_BLOCK = 256


class AudioClip:
    """A sound for a pipeline input: the filters receive ``signal``, the timeline shows its waveform.

    Args:
        source: an audio file (WAV with the standard library, other formats
            through ``ffmpeg``: see ``sound.load``), or a numpy signal, mono
            ``(n,)`` or ``(n, channels)``, float in ``[-1, 1]`` or ``int16``.
        sample_rate: a file: resample to this rate (default: the file's);
            a numpy signal: its rate, required. Give several clips the same
            rate to mix them sample by sample.
        mono: a file: average its channels (default); ``False`` keeps
            ``(n, channels)``.
        start: a file: skip this many seconds.
        duration: a file: keep at most this many seconds.
        timeline: how the Qt and Dear PyGui windows show the timeline, as for
            ``Video``: ``"shown"``, ``"collapsible"``, ``"collapsed"`` or
            ``"hidden"`` (the first timeline input decides).
        play: play this clip when no filter calls ``audio.set`` (the first
            ``AudioClip`` input plays by default; ``False`` keeps it silent).
        description: shown by ``repr`` (default: the file name).

    Attributes:
        signal: float32 ``(n,)`` or ``(n, channels)`` in ``[-1, 1]``.
        sample_rate: Hz.
        duration: seconds.
    """

    def __init__(
        self,
        source: Union[str, os.PathLike[str], np.ndarray],
        sample_rate: Optional[int] = None,
        *,
        mono: bool = True,
        start: float = 0.0,
        duration: Optional[float] = None,
        timeline: str = "shown",
        play: bool = True,
        description: Optional[str] = None,
    ) -> None:
        from interactive_pipe.data_objects.video import TIMELINE_DISPLAYS

        if timeline not in TIMELINE_DISPLAYS:
            raise ValueError(
                f"AudioClip: timeline must be one of {', '.join(map(repr, TIMELINE_DISPLAYS))}, got {timeline!r}"
            )
        if isinstance(source, (str, os.PathLike)):
            from interactive_pipe import sound

            if sample_rate is not None and (not isinstance(sample_rate, (int, np.integer)) or sample_rate <= 0):
                raise ValueError(f"AudioClip: sample_rate must be a positive integer (Hz), got {sample_rate!r}")
            self.path: Optional[Path] = Path(source)
            signal, rate = sound.load(self.path, sample_rate=sample_rate, mono=mono, start=start, duration=duration)
            default_description = self.path.name
        elif isinstance(source, np.ndarray):
            if sample_rate is None:
                raise TypeError("AudioClip(signal, sample_rate): a numpy signal needs its sample rate in Hz")
            if not isinstance(sample_rate, (int, np.integer)) or sample_rate <= 0:
                raise ValueError(f"AudioClip: sample_rate must be a positive integer (Hz), got {sample_rate!r}")
            if source.ndim not in (1, 2) or (source.ndim == 2 and source.shape[1] not in (1, 2)):
                hint = " (pass signal.T: channels go last)" if source.ndim == 2 and source.shape[0] <= 2 else ""
                raise ValueError(f"AudioClip: a signal is (n,) or (n, channels), got shape {source.shape}{hint}")
            if source.dtype == np.int16:
                signal = source.astype(np.float32) / 32768.0
            elif source.dtype.kind == "f":
                signal = source.astype(np.float32, copy=False)
            else:
                raise TypeError(f"AudioClip: a signal is float in [-1, 1] or int16, got dtype {source.dtype}")
            rate = int(sample_rate)
            self.path = None
            default_description = "signal"
        else:
            raise TypeError(
                f"AudioClip: got {type(source).__name__}; give a file path, or a numpy signal and its sample_rate"
            )
        if len(signal) == 0:
            raise ValueError(f"AudioClip: {default_description} holds no sample")
        self.signal: np.ndarray = signal
        self.sample_rate: int = int(rate)
        self.timeline_display: str = timeline
        self.play: bool = bool(play)
        self.description: str = description if description is not None else default_description
        self._peaks: Optional[Tuple[np.ndarray, np.ndarray]] = None

    def __len__(self) -> int:
        """Number of samples."""
        return len(self.signal)

    @property
    def duration(self) -> float:
        return len(self.signal) / self.sample_rate

    @property
    def channels(self) -> int:
        return 1 if self.signal.ndim == 1 else int(self.signal.shape[1])

    def metadata(self) -> Dict[str, Any]:
        """What ``context["timeline"].inputs_metadata[name]`` holds for this input."""
        meta: Dict[str, Any] = {"sample_rate": self.sample_rate, "duration": self.duration, "channels": self.channels}
        if self.path is not None:
            meta["path"] = str(self.path)
        return meta

    # ---------------------------------------------------------------- waveform
    def _envelope(self) -> Tuple[np.ndarray, np.ndarray]:
        """``(|signal|, block peaks)``: the absolute mono signal and its maximum per ``PEAK_BLOCK`` samples.

        Both end with an extra 0 (``_span_max`` reads up to one past the end without copying them).
        """
        if self._peaks is None:
            magnitude = np.abs(self.signal).astype(np.float32)
            if magnitude.ndim == 2:
                magnitude = magnitude.max(axis=1)
            n_blocks = -(-len(magnitude) // PEAK_BLOCK)
            padded = np.zeros(n_blocks * PEAK_BLOCK, dtype=np.float32)
            padded[: len(magnitude)] = magnitude
            blocks = padded.reshape(n_blocks, PEAK_BLOCK).max(axis=1)
            self._peaks = (np.append(magnitude, np.float32(0.0)), np.append(blocks, np.float32(0.0)))
        return self._peaks

    def peaks(self, start: float, stop: float, columns: int) -> np.ndarray:
        """Peak amplitude in ``[0, 1]`` of each of ``columns`` equal spans of time from ``start`` to ``stop`` (s).

        Spans after the end of the clip are 0. Uses the block peaks when a
        span covers several blocks, so a long clip draws as fast as a short one.
        """
        columns = max(int(columns), 1)
        out = np.zeros(columns, dtype=np.float32)
        if stop <= start:
            return out
        magnitude, blocks = self._envelope()
        n_samples = len(magnitude) - 1  # without the trailing 0
        edges = start + (stop - start) * np.arange(columns + 1) / columns
        samples = np.round(edges * self.sample_rate).astype(np.int64)
        inside = (samples[:-1] < n_samples) & (samples[1:] > 0)
        if not inside.any():
            return out
        first = np.clip(samples[:-1], 0, n_samples - 1)[inside]
        last = np.maximum(np.clip(samples[1:], 1, n_samples)[inside], first + 1)
        if np.median(last - first) < 2 * PEAK_BLOCK:  # zoomed in: the samples themselves
            values = _span_max(magnitude, first, last)
        else:
            # whole blocks inside each span from the block peaks, the two partial ends from the samples
            inner_first = -(-first // PEAK_BLOCK)
            inner_last = last // PEAK_BLOCK
            has_inner = inner_last > inner_first
            head_end = np.where(has_inner, inner_first * PEAK_BLOCK, last)
            tail_start = np.where(has_inner, inner_last * PEAK_BLOCK, last)
            values = _short_span_max(magnitude, first, head_end)
            tail = _short_span_max(magnitude, tail_start, last)
            inner = _span_max(blocks, inner_first, np.maximum(inner_last, inner_first + 1))
            values = np.maximum(values, tail)
            values = np.maximum(values, np.where(has_inner, inner, 0.0))
        out[inside] = values
        return np.clip(out, 0.0, 1.0)

    def __repr__(self) -> str:
        channels = "" if self.channels == 1 else f", {self.channels} channels"
        return f"AudioClip({self.description}, {self.duration:.2f} s at {self.sample_rate} Hz{channels})"


def _span_max(padded: np.ndarray, first: np.ndarray, last: np.ndarray) -> np.ndarray:
    """``padded[first[k]:last[k]].max()`` for every k, vectorised.

    ``padded`` ends with an extra element, so ``last`` may be one past the
    real end (``first < last <= len(padded) - 1``).
    """
    pairs = np.stack([np.minimum(first, len(padded) - 2), last], axis=1).ravel()
    # a view ending one past the last span: the final index of reduceat reduces up to the end of the array
    return np.maximum.reduceat(padded[: int(last.max()) + 1], pairs)[::2]


def _short_span_max(padded: np.ndarray, first: np.ndarray, last: np.ndarray) -> np.ndarray:
    """``padded[first[k]:last[k]].max()`` (0 when empty) for spans shorter than ``PEAK_BLOCK``: a gather."""
    index = first[:, None] + np.arange(PEAK_BLOCK)[None, :]
    values = padded[np.minimum(index, len(padded) - 1)]
    return np.where(index < last[:, None], values, 0.0).max(axis=1)


def is_audio_clip(value: Any) -> bool:
    return isinstance(value, AudioClip)
