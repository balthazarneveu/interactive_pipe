"""Streamed playback of numpy signals for the Qt backend (Qt 6: PyQt6 / PySide6).

A ``QAudioSink`` pulls samples from a :class:`SignalMixer` through a small
``QIODevice``. Both live in a dedicated thread with its own event loop, so
the audio keeps flowing while the GUI thread runs the pipeline; filters only
swap the mixer's signal (a lock, no Qt call across threads).

The sink is opened once in the output device's preferred format (rate,
channels; float samples when supported, else 16-bit): signals are converted
when set, so changing a sound never reopens the device.
"""

import logging
import threading
from typing import Optional

import numpy as np

from interactive_pipe.core.audio_mixer import SignalMixer

BUFFER_MS = 120  # sink buffer: latency of a change vs. headroom for a busy GUI thread

try:  # Qt 6 only: QAudioSink does not exist in Qt 5
    from PyQt6.QtCore import QIODevice, QThread
    from PyQt6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices
except ImportError:  # pragma: no cover - depends on the installed binding
    try:
        from PySide6.QtCore import QIODevice, QThread  # type: ignore[assignment]
        from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices  # type: ignore[assignment]
    except ImportError:
        QAudioSink = None  # type: ignore[assignment,misc]


def available() -> bool:
    """A Qt 6 binding with QtMultimedia and an audio output device."""
    if QAudioSink is None:
        return False
    try:
        return not QMediaDevices.defaultAudioOutput().isNull()
    except Exception:  # noqa: BLE001 - no multimedia backend at all
        return False


if QAudioSink is not None:

    class _PullDevice(QIODevice):  # type: ignore[misc,valid-type]
        """Sequential read-only device: every read renders the next block of the mixer."""

        def __init__(self, mixer: SignalMixer, int16: bool):
            super().__init__()
            self.mixer = mixer
            self.int16 = int16
            self.frame_bytes = mixer.channels * (2 if int16 else 4)

        def isSequential(self):
            return True

        def bytesAvailable(self):
            return 1 << 20  # endless stream

        def readData(self, maxlen):
            count = int(maxlen) // self.frame_bytes
            if count <= 0:
                return b""
            frames = self.mixer.render(count)
            if self.int16:
                return (np.clip(frames, -1.0, 1.0) * 32767).astype("<i2").tobytes()
            return frames.astype("<f4").tobytes()

        def writeData(self, data):
            return -1

    class _AudioThread(QThread):  # type: ignore[misc,valid-type]
        def __init__(self, mixer: SignalMixer, audio_format, volume: float):
            super().__init__()
            self.mixer = mixer
            self.audio_format = audio_format
            self.volume = volume
            self.started_event = threading.Event()
            self.error: Optional[str] = None

        def run(self):
            # Created here: the sink's timers and the device reads run in this thread
            try:
                int16 = self.audio_format.sampleFormat() == QAudioFormat.SampleFormat.Int16
                device = _PullDevice(self.mixer, int16)
                device.open(QIODevice.OpenModeFlag.ReadOnly)
                sink = QAudioSink(QMediaDevices.defaultAudioOutput(), self.audio_format)  # type: ignore[reportOptionalCall]  # defined in this branch
                sink.setBufferSize(int(self.audio_format.bytesForDuration(BUFFER_MS * 1000)))
                sink.setVolume(self.volume)
                sink.start(device)
            except Exception as exc:  # noqa: BLE001 - reported to the GUI thread
                self.error = repr(exc)
                self.started_event.set()
                return
            self.started_event.set()
            self.exec()
            sink.stop()
            device.close()


class QtSignalStream:
    """Plays numpy signals with sample-accurate, click-free swaps (see :class:`SignalMixer`)."""

    def __init__(self, volume: float = 0.5):
        if QAudioSink is None:
            raise RuntimeError("audio streaming needs Qt 6 (PyQt6 or PySide6) with QtMultimedia")
        output = QMediaDevices.defaultAudioOutput()
        preferred = output.preferredFormat()
        audio_format = QAudioFormat()
        audio_format.setSampleRate(preferred.sampleRate())
        audio_format.setChannelCount(min(max(preferred.channelCount(), 1), 2))
        audio_format.setSampleFormat(QAudioFormat.SampleFormat.Float)
        if not output.isFormatSupported(audio_format):
            audio_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self.mixer = SignalMixer(audio_format.sampleRate(), audio_format.channelCount())
        self._thread = _AudioThread(self.mixer, audio_format, volume)
        self._thread.start()
        self._thread.started_event.wait(2.0)
        if self._thread.error is not None:
            raise RuntimeError(f"cannot open the audio output: {self._thread.error}")

    def set(self, signal: np.ndarray, sample_rate: int, keep_position: bool = True, loop: bool = False) -> None:
        self.mixer.set(signal, sample_rate, keep_position=keep_position, loop=loop)

    def play(self) -> None:
        self.mixer.play()

    def pause(self) -> None:
        self.mixer.pause()

    def stop(self) -> None:
        self.mixer.stop()

    def seek(self, seconds: float) -> None:
        self.mixer.seek(seconds)

    def position(self) -> float:
        return self.mixer.position_seconds

    def playing(self) -> bool:
        return self.mixer.playing

    def close(self) -> None:
        """Stop the audio thread (called when the application quits)."""
        if self._thread.isRunning():
            self.mixer.stop()
            self._thread.quit()
            if not self._thread.wait(2000):
                logging.warning("audio thread did not stop in time")
