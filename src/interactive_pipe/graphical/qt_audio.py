"""Audio playback for the Qt GUI backend.

:class:`QtAudioPlayer` serves the context ``audio`` proxy (``load_audio``,
``play``, ``pause``, ``stop``) with two engines:

- **numpy signals** are streamed from memory (Qt 6, :mod:`qt_audio_stream`):
  a new version of the sound continues at the same sample with a short
  cross-fade, in an audio thread of its own, so tweaking a slider while
  listening is fluid;
- **files** (and signals under Qt 5) play through a ``QMediaPlayer``; a kept
  position is sought once the new file is loaded.
"""

import atexit
import logging
import os
import tempfile
import wave
from pathlib import Path
from typing import Optional

import numpy as np

from interactive_pipe.core.framework_state import AudioRequest
from interactive_pipe.graphical import qt_audio_stream
from interactive_pipe.graphical.qt_backend import (
    PYQTVERSION,
    QAudioOutput,
    QMediaContent,
    QMediaPlayer,
    QUrl,
)

VOLUME = 0.5  # linear, in [0, 1]
END_MARGIN_MS = 50  # a kept position this close to the end starts the new file from the beginning


def _media_status(name):
    enum = getattr(QMediaPlayer, "MediaStatus", QMediaPlayer)  # Qt6 scoped enum, Qt5 flat
    return getattr(enum, name)


_LOADED_STATUSES = (_media_status("LoadedMedia"), _media_status("BufferedMedia"))


class _FilePlayer:
    """A QMediaPlayer playing files, optionally resuming at the previous position."""

    def __init__(self):
        self.media_player = QMediaPlayer()
        if PYQTVERSION == 6:
            self.audio_output = QAudioOutput()
            self.media_player.setAudioOutput(self.audio_output)
            self.audio_output.setVolume(VOLUME)
            self.media_player.errorChanged.connect(self.handle_error)  # type: ignore[reportAttributeAccessIssue]
        else:
            self.media_player.setVolume(int(100 * VOLUME))  # type: ignore[reportAttributeAccessIssue]
            self.media_player.error.connect(self.handle_error)  # type: ignore[reportAttributeAccessIssue]
        self._pending_position: Optional[int] = None  # sought once the new file is loaded (asynchronous)
        self._play_when_loaded = False
        self.media_player.mediaStatusChanged.connect(self._on_media_status)  # type: ignore[reportAttributeAccessIssue]

    def handle_error(self, *_args):
        logging.error(f"Audio player error: {self.media_player.errorString()}")

    def load(self, file_path, keep_position=False, loop=False):
        path = Path(file_path)
        path = path.resolve() if path.is_absolute() else Path.cwd() / path
        if not path.exists():
            raise FileNotFoundError(f"Audio file does not exist: {path}")
        position = self.media_player.position() if keep_position else 0
        self.stop()
        self._pending_position = position if position > 0 else None
        url = QUrl.fromLocalFile(str(path))
        if PYQTVERSION == 6:
            self.media_player.setLoops(-1 if loop else 1)  # type: ignore[reportAttributeAccessIssue]  # -1: Infinite
            self.media_player.setSource(url)  # type: ignore[reportAttributeAccessIssue]
        else:
            self.media_player.setMedia(QMediaContent(url))  # type: ignore[reportAttributeAccessIssue]
            if self._pending_position is None:
                self.media_player.play()  # Qt5 behaviour kept: setMedia starts playing
        if self._pending_position is None:
            self.media_player.setPosition(0)
        else:
            self._on_media_status(self.media_player.mediaStatus())  # already loaded (synchronous backends)

    def _on_media_status(self, status):
        if self._pending_position is None or status not in _LOADED_STATUSES:
            return
        position, self._pending_position = self._pending_position, None
        duration = self.media_player.duration()
        if duration > 0 and position >= duration - END_MARGIN_MS:
            position = 0  # past the end of the new file: from the beginning
        self.media_player.setPosition(position)
        if self._play_when_loaded:
            self._play_when_loaded = False
            self.media_player.play()

    def play(self):
        if self._pending_position is not None:
            self._play_when_loaded = True  # starting now would play the beginning before the seek
            return
        self.media_player.play()

    def pause(self):
        self.media_player.pause()

    def stop(self):
        self._play_when_loaded = False
        self.media_player.stop()


class _WavFallback:
    """Signals written to a temporary WAV for the media player (no streaming available)."""

    def __init__(self):
        self.path: Optional[str] = None
        atexit.register(self.remove)

    def write(self, frames: np.ndarray, rate: int) -> str:
        self.remove()
        handle, path = tempfile.mkstemp(prefix="interactive_pipe_audio_", suffix=".wav")
        os.close(handle)
        with wave.open(path, "wb") as wav:
            wav.setnchannels(frames.shape[1])
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes((np.clip(frames, -1, 1) * 32767).astype("<i2").tobytes())
        self.path = path
        return path

    def remove(self):
        if self.path is not None:
            try:
                os.remove(self.path)
            except OSError:
                pass
            self.path = None


class QtAudioPlayer:
    def __init__(self, file_player_factory=_FilePlayer, stream_factory=None):
        self.files = file_player_factory()
        if stream_factory is None and qt_audio_stream.available():
            stream_factory = qt_audio_stream.QtSignalStream
        self._stream_factory = stream_factory
        self._stream = None
        self._wav_fallback = _WavFallback()
        self.active = self.files

    @property
    def accepts_signals(self) -> bool:
        """Numpy signals can be streamed (Qt 6 with an audio output)."""
        return self._stream_factory is not None

    @property
    def media_player(self):
        return self.files.media_player

    def _get_stream(self):
        if self._stream is None and self._stream_factory is not None:
            try:
                self._stream = self._stream_factory()
            except Exception as exc:  # noqa: BLE001 - no device, busy device...
                logging.error(f"Audio streaming unavailable ({exc}): signals play as files, without live swaps")
                self._stream_factory = None
        return self._stream

    def load(self, request: AudioRequest):
        """The ``load_audio`` binding: one sound to play (see :class:`AudioRequest`)."""
        path = request.path
        if request.signal is not None:
            if request.sample_rate is None:
                raise ValueError("AudioRequest: a signal needs its sample_rate")
            stream = self._get_stream()
            if stream is not None:
                if self.active is not stream:
                    self.files.stop()
                    self.active = stream
                stream.set(request.signal, request.sample_rate, keep_position=request.keep_position, loop=request.loop)
                return
            path = self._wav_fallback.write(request.signal, request.sample_rate)
        if self._stream is not None:
            self._stream.stop()
        self.active = self.files
        self.files.load(path, keep_position=request.keep_position, loop=request.loop)

    def set_audio(self, file_path, keep_position=False):
        """Legacy binding: a file, from its start unless ``keep_position``."""
        self.load(AudioRequest(path=str(file_path), keep_position=keep_position))

    def play(self):
        self.active.play()

    def pause(self):
        self.active.pause()

    def stop(self):
        self.active.stop()

    def close(self):
        """Release the audio thread (application exit)."""
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        self._wav_fallback.remove()
