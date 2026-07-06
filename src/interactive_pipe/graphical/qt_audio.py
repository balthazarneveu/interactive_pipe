"""Qt media-player wrapper for the audio feature of the Qt GUI backend.

Extracted from qt_gui.py (tech-debt item 1). Wraps QMediaPlayer with the
PYQTVERSION-conditional setup and exposes the four callbacks the context
audio proxy needs (set_audio/play/pause/stop).
"""

import logging
from pathlib import Path

from interactive_pipe.graphical.qt_backend import (
    PYQTVERSION,
    QAudioOutput,
    QMediaContent,
    QMediaPlayer,
    QUrl,
)


class QtAudioPlayer:
    def __init__(self):
        self.media_player = QMediaPlayer()
        if PYQTVERSION == 6:
            self.audio_output = QAudioOutput()
            self.media_player.setAudioOutput(self.audio_output)
            self.audio_output.setVolume(50)
            self.media_player.errorChanged.connect(self.handle_error)  # type: ignore[reportAttributeAccessIssue]
        else:
            self.media_player.setVolume(50)  # type: ignore[reportAttributeAccessIssue]
            self.media_player.error.connect(self.handle_error)  # type: ignore[reportAttributeAccessIssue]

    def handle_error(self):
        logging.error(f"Audio player error: {self.media_player.errorString()}")

    def set_audio(self, file_path):
        self.stop()
        if isinstance(file_path, str):
            file_path = Path(file_path)
        if not file_path.is_absolute():
            file_path = Path.cwd() / file_path
        else:
            file_path = file_path.resolve()
        if not file_path.exists():
            raise FileNotFoundError(f"Audio file does not exist: {file_path}")
        media_url = QUrl.fromLocalFile(str(file_path))
        if PYQTVERSION == 6:
            self.media_player.setSource(media_url)  # type: ignore[reportAttributeAccessIssue]
        else:
            content = QMediaContent(media_url)  # type: ignore[reportAssignmentType]
            self.media_player.setMedia(content)  # type: ignore[reportAttributeAccessIssue]
            self.media_player.play()
        self.media_player.setPosition(0)

    def play(self):
        self.media_player.play()

    def pause(self):
        self.media_player.pause()

    def stop(self):
        self.media_player.stop()
