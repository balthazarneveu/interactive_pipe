"""QtAudioPlayer: signals go to the stream, files to the media player; failures degrade quietly."""

import os

import numpy as np
import pytest

pytest.importorskip("PyQt6.QtMultimedia")

from interactive_pipe.core.framework_state import AudioRequest  # noqa: E402
from interactive_pipe.graphical import qt_audio  # noqa: E402


class FakeEngine:
    def __init__(self):
        self.calls = []

    def load(self, path, keep_position=False, loop=False):
        self.calls.append(("load", path, keep_position, loop))

    def set(self, signal, rate, keep_position=True, loop=False):
        self.calls.append(("set", signal.shape, rate, keep_position, loop))

    def play(self):
        self.calls.append(("play",))

    def pause(self):
        self.calls.append(("pause",))

    def stop(self):
        self.calls.append(("stop",))

    def close(self):
        self.calls.append(("close",))


SIGNAL = AudioRequest(signal=np.zeros((10, 1), np.float32), sample_rate=8000, keep_position=True, loop=True)
FILE = AudioRequest(path="track.wav", keep_position=False, loop=False)


@pytest.fixture
def engines():
    files, stream, created = FakeEngine(), FakeEngine(), []

    def make_stream():
        created.append(stream)
        return stream

    player = qt_audio.QtAudioPlayer(file_player_factory=lambda: files, stream_factory=make_stream)
    return player, files, stream, created


def test_the_stream_is_created_on_the_first_signal_only(engines):
    player, files, stream, created = engines
    assert player.accepts_signals and not created
    player.load(FILE)
    assert not created
    player.load(SIGNAL)
    player.load(SIGNAL)
    assert created == [stream]


def test_signals_go_to_the_stream_files_to_the_media_player(engines):
    player, files, stream, _ = engines
    player.load(SIGNAL)
    player.play()
    assert stream.calls == [("set", (10, 1), 8000, True, True), ("play",)]
    player.load(FILE)
    player.play()
    assert stream.calls[-1] == ("stop",)  # the streamed sound stops when a file takes over
    assert files.calls[-2:] == [("load", "track.wav", False, False), ("play",)]
    player.load(SIGNAL)
    assert ("stop",) in files.calls
    player.pause()
    assert stream.calls[-1] == ("pause",)


def test_close_releases_the_stream(engines):
    player, _files, stream, _ = engines
    player.load(SIGNAL)
    player.close()
    player.close()  # idempotent
    assert stream.calls.count(("close",)) == 1


def test_a_stream_that_cannot_open_is_reported_once_and_signals_play_as_files(caplog):
    attempts = []

    def failing():
        attempts.append(1)
        raise RuntimeError("device busy")

    files = FakeEngine()
    player = qt_audio.QtAudioPlayer(file_player_factory=lambda: files, stream_factory=failing)
    player.load(SIGNAL)
    player.load(SIGNAL)
    player.play()
    assert len(attempts) == 1 and not player.accepts_signals
    assert "device busy" in caplog.text
    loads = [call for call in files.calls if call[0] == "load"]
    assert len(loads) == 2 and loads[-1][1].endswith(".wav") and loads[-1][2:] == (True, True)
    assert os.path.exists(loads[-1][1]) and not os.path.exists(loads[0][1])  # one temporary file at a time
    player.close()
    assert not os.path.exists(loads[-1][1])


def test_legacy_set_audio_loads_a_file(engines):
    player, files, _stream, _ = engines
    player.set_audio("a.wav")
    assert files.calls == [("load", "a.wav", False, False)]
