from pathlib import Path
import numpy as np
from io import BytesIO
import base64
import logging
from typing import Union, Tuple
WAVIO_AVAILABLE = False
try:
    WAVIO_AVAILABLE = True
    import wavio
except ImportError:
    logging.info("Cannot import wavio")


def audio_to_html(audio: Union[None, str, Path, Tuple[int, np.ndarray]], controls=True) -> str:
    if audio is None:
        logging.debug("No audio to display")
        return ""
    if isinstance(audio, str) or isinstance(audio, Path):
        audio_base64 = base64.b64encode(open(audio, "rb").read()).decode("utf-8")
    elif isinstance(audio, tuple):
        assert WAVIO_AVAILABLE, "wavio is not available"
        assert len(audio) == 2, "audio tuple should have 2 elements: (rate, data)"
        assert isinstance(audio[0], int), "audio[0] should be an integer"
        assert isinstance(audio[1], np.ndarray), "audio[1] should be a numpy array"
        audio_bytes = BytesIO()
        wavio.write(audio_bytes, audio[1].astype(np.float32), audio[0], sampwidth=4)
        audio_bytes.seek(0)
        audio_base64 = base64.b64encode(audio_bytes.read()).decode("utf-8")
    audio_player = f'<audio src="data:audio/mpeg;base64,{audio_base64}"'
    if controls:
        audio_player += ' controls'
    audio_player += ' autoplay></audio>'

    return audio_player
