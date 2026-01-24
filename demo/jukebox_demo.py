from interactive_pipe import Control, interactive, interactive_pipeline
from interactive_pipe.data_objects.image import Image
from pathlib import Path
import cv2
import argparse

root = Path(__file__).parent
img_folder = root / "images"
audio_folder = root / "audio"
TRACK = "track"
IMAGE = ICON = "image"
CAPTION = "caption"

TRACK_DICT = {
    "elephant": {
        TRACK: audio_folder / "elephant.mp4",
        CAPTION: "ELEPHANT",
    },
    "snail": {
        TRACK: audio_folder / "snail.mp4",
        CAPTION: "SNAIL",
    },
    "rabbit": {
        TRACK: audio_folder / "rabbit.mp4",
        CAPTION: "RABBIT",
    },
    "pause": {TRACK: None, CAPTION: "...zzzz"},
}

for item_name in TRACK_DICT.keys():
    TRACK_DICT[item_name][IMAGE] = img_folder / (item_name + ".png")
ICONS = [it[ICON] for key, it in TRACK_DICT.items()]


@interactive(song=Control("elephant", list(TRACK_DICT.keys()), icons=ICONS))
def song_choice(song="elephant"):
    # Can use dict-style or attribute-style access
    context[TRACK] = song


def play_song():
    song = context.get(TRACK, None)
    first_exec = context.get("first_exec", True)
    if not first_exec:
        audio_track = TRACK_DICT[song][TRACK]
        if audio_track is None:
            audio.stop()
        else:
            audio.set(audio_track)
            audio.play()
    else:
        # Attribute-style access
        context.first_exec = False


def image_choice():
    song = context.get(TRACK, list(TRACK_DICT.keys())[0])
    img = Image.from_file(TRACK_DICT[song][IMAGE]).data
    max_height = 300
    h, w, _c = img.shape
    if h > max_height:
        img = cv2.resize(img, (w * max_height // h, max_height))
        h, w, _c = img.shape
    caption = TRACK_DICT[song][CAPTION]
    layout.style("img_out", title=caption)
    return img


def sample_pipeline():
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
    interactive_pipeline(gui=args.backend, cache=False, name="music", audio=True)(
        sample_pipeline
    )()
