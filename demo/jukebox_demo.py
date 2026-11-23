"""Jukebox demo: touch an icon to play the matching music track (audio + image buttons)"""

import argparse
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional

import cv2
import numpy as np

from interactive_pipe import (
    Control,
    Image,
    audio,
    context,
    interactive,
    interactive_pipeline,
    layout,
)

root = Path(__file__).parent
img_folder = root / "images"
audio_folder = root / "audio"
TRACK = "track"


class Track(NamedTuple):
    caption: str
    sound: Optional[Path]  # None: silence
    image: Path


TRACKS: Dict[str, Track] = {
    name: Track(caption, sound, img_folder / f"{name}.png")
    for name, caption, sound in [
        ("elephant", "ELEPHANT", audio_folder / "elephant.mp4"),
        ("snail", "SNAIL", audio_folder / "snail.mp4"),
        ("rabbit", "RABBIT", audio_folder / "rabbit.mp4"),
        ("pause", "...zzzz", None),
    ]
}
ICONS: List[Path] = [track.image for track in TRACKS.values()]


@interactive(song=Control("elephant", list(TRACKS), icons=ICONS))
def song_choice(song: str = "elephant") -> None:
    # Can use dict-style or attribute-style access
    context[TRACK] = song


def play_song() -> None:
    song = context.get(TRACK, None)
    first_exec = context.get("first_exec", True)
    if not first_exec:
        audio_track = TRACKS[song].sound
        if audio_track is None:
            audio.stop()
        else:
            audio.set(audio_track)
            audio.play()
    else:
        # Attribute-style access
        context.first_exec = False


def image_choice() -> np.ndarray:
    song = context.get(TRACK, "elephant")
    img = Image.load_image(TRACKS[song].image)
    max_height = 300
    h, w, _c = img.shape
    if h > max_height:
        img = cv2.resize(img, (w * max_height // h, max_height))
        h, w, _c = img.shape
    layout.style("img_out", title=TRACKS[song].caption)
    return img


def sample_pipeline() -> List[np.ndarray]:
    song_choice()
    play_song()
    img_out = image_choice()
    return [
        img_out,
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Jukebox demo with backend selection")
    parser.add_argument(
        "-b",
        "--backend",
        type=str,
        choices=["qt", "gradio"],
        default="qt",
        help="Backend to use: qt or gradio (default: qt)",
    )
    args = parser.parse_args()
    interactive_pipeline(gui=args.backend, cache=False, name="music", audio=True)(sample_pipeline)()
