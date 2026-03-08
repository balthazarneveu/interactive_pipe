import argparse
from pathlib import Path

import cv2

from interactive_pipe import Control, context, interactive, interactive_pipeline, layout
from interactive_pipe.data_objects.image import Image

root = Path(__file__).parent
img_folder = root / "images"
SELECTION = "selection"
IMAGE = ICON = "image"
CAPTION = "caption"

SELECTION_DICT = {
    "elephant": {
        CAPTION: "ELEPHANT",
    },
    "snail": {
        CAPTION: "SNAIL",
    },
    "rabbit": {
        CAPTION: "RABBIT",
    },
    "pause": {CAPTION: "...zzzz"},
}

for item_name in SELECTION_DICT.keys():
    SELECTION_DICT[item_name][IMAGE] = img_folder / (item_name + ".png")
ICONS = [it[ICON] for key, it in SELECTION_DICT.items()]


@interactive(selection=Control("elephant", list(SELECTION_DICT.keys()), icons=ICONS))
def selection_choice(selection="elephant"):
    context[SELECTION] = selection


def handle_selection():
    selection = context.get(SELECTION, None)
    first_exec = context.get("first_exec", True)
    if not first_exec:
        caption = SELECTION_DICT[selection][CAPTION]
        print(f"Selected: {selection}")
        print(f"  Caption: {caption}")
    else:
        context["first_exec"] = False


def image_choice():
    selection = context.get(SELECTION, list(SELECTION_DICT.keys())[0])
    img = Image.from_file(SELECTION_DICT[selection][IMAGE]).data
    max_height = 300  # Raspberry pi with a 7" touchscreen
    h, w, _c = img.shape
    if h > max_height:
        img = cv2.resize(img, (w * max_height // h, max_height))
        h, w, _c = img.shape
    caption = SELECTION_DICT[selection][CAPTION]
    layout.style("img_out", title=caption)  # discard auto titling
    return img


def sample_pipeline():
    selection_choice()
    handle_selection()
    img_out = image_choice()
    return [
        img_out,
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Button demo with backend selection")
    parser.add_argument(
        "-b",
        "--backend",
        type=str,
        choices=["qt", "gradio", "mpl", "dpg"],
        default="qt",
        help="Backend to use: qt, gradio, mpl, or dpg (default: qt)",
    )
    args = parser.parse_args()
    interactive_pipeline(gui=args.backend)(sample_pipeline)()
