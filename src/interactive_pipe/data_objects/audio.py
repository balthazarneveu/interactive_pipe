from pathlib import Path
from interactive_pipe.data_objects.data import Data
import numpy as np
from io import BytesIO
import base64
import logging
from typing import Union, Tuple

WAVIO_AVAILABLE = False
WAVIO = "wavio"
try:
    WAVIO_AVAILABLE = True
    import wavio
except ImportError:
    logging.info("Cannot import wavio")

__iter_audio_player = 0


def audio_to_html(
    audio: Union[None, str, Path, Tuple[int, np.ndarray]], controls=True
) -> str:
    if audio is None:
        logging.debug("No audio to display")
        return ""
    if isinstance(audio, str) or isinstance(audio, Path):
        audio_base64 = base64.b64encode(open(str(audio), "rb").read()).decode("utf-8")
    elif isinstance(audio, tuple):
        if not WAVIO_AVAILABLE:
            raise RuntimeError("wavio is not available")
        if len(audio) != 2:
            raise ValueError(
                f"audio tuple should have 2 elements: (rate, data), got {len(audio)}"
            )
        if not isinstance(audio[0], int):
            raise TypeError(f"audio[0] should be an integer, got {type(audio[0])}")
        if not isinstance(audio[1], np.ndarray):
            raise TypeError(f"audio[1] should be a numpy array, got {type(audio[1])}")
        audio_bytes = BytesIO()
        wavio.write(audio_bytes, audio[1].astype(np.float32), audio[0], sampwidth=4)
        audio_bytes.seek(0)
        audio_base64 = base64.b64encode(audio_bytes.read()).decode("utf-8")
    audio_player = f'<audio src="data:audio/mpeg;base64,{audio_base64}"'
    if controls:
        audio_player += " controls"
    audio_player += " autoplay></audio>"
    global __iter_audio_player
    # to avoid reusing the same exact id and thus not updating the audio player
    audio_player += "<p hidden>" + str(__iter_audio_player) + "</p>"
    __iter_audio_player += 1

    return audio_player


class Audio(Data):
    def __init__(self, data, sampling_rate: int = None, title="") -> None:
        super().__init__(data)
        self.title = title
        self.path = None
        self.sampling_rate = sampling_rate

    def _set_file_extensions(self):
        self.file_extensions = [".wav", ".mp3", ".mp4"]

    def _save(self, path: Path, backend=None):
        if path is None:
            raise ValueError("Save requires a path")
        if self.title is not None:
            self.path = self.append_with_stem(path, self.title)
        else:
            self.path = path
        self.save_audio(self.data, self.path, self.sampling_rate, backend=backend)

    def _load(self, path: Path, backend=None, title=None) -> Tuple[int, np.ndarray]:
        if title is not None:
            self.title = title
        self.path = path
        self.sampling_rate, audio_data = self.load_audio(path, backend=backend)
        return self.sampling_rate, audio_data

    @staticmethod
    def save_audio(data, path: Path, sampling_rate=None, backend=None):
        if backend is None:
            backend = WAVIO
        if backend == WAVIO:
            if isinstance(data, np.ndarray):
                if data.dtype == np.float32 or data.dtype == np.float64:
                    data_save = (data * 32767).astype(np.int16)
                elif data.dtype == np.int16:
                    data_save = data
                else:
                    raise ValueError(f"Data type {data.dtype} not supported")
            if not WAVIO_AVAILABLE:
                raise RuntimeError("wavio is not available")
            wavio.write(path, data_save, sampling_rate)
        else:
            raise NotImplementedError(f"Unknown backend: {backend}")

    @staticmethod
    def load_audio(path: Path, backend=None) -> np.ndarray:
        if backend is None:
            backend = WAVIO
        if backend == WAVIO:
            if not WAVIO_AVAILABLE:
                raise RuntimeError("wavio is not available")
            audio = wavio.read(str(path))
            return audio.rate, audio.data
        else:
            raise NotImplementedError(f"Unknown backend: {backend}")


if __name__ == "__main__":
    audio_sample_path = Path("demo") / "audio" / "rabbit.mp4"
    rate, data = Audio.load_audio(audio_sample_path)
