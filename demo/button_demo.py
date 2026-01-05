from interactive_pipe import Control
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.graphical.qt_gui import InteractivePipeQT
from interactive_pipe import interactive
from interactive_pipe.data_objects.image import Image
from pathlib import Path
import cv2

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
def selection_choice(global_params={}, selection="elephant"):
    global_params[SELECTION] = selection


def handle_selection(global_params={}):
    selection = global_params.get(SELECTION, None)
    first_exec = global_params.get("first_exec", True)
    if not first_exec:
        caption = SELECTION_DICT[selection][CAPTION]
        print(f"Selected: {selection}")
        print(f"  Caption: {caption}")
    else:
        global_params["first_exec"] = False


def image_choice(global_params={}):
    selection = global_params.get(SELECTION, list(SELECTION_DICT.keys())[0])
    img = Image.from_file(SELECTION_DICT[selection][IMAGE]).data
    max_height = 300  # Raspberry pi with a 7" touchscreen
    h, w, _c = img.shape
    if h > max_height:
        img = cv2.resize(img, (w * max_height // h, max_height))
        h, w, _c = img.shape
    caption = SELECTION_DICT[selection][CAPTION]
    global_params["__output_styles"]["img_out"] = {
        "title": caption
    }  # discard auto titling
    return img


def sample_pipeline():
    selection_choice()
    handle_selection()
    img_out = image_choice()
    return [
        img_out,
    ]


if __name__ == "__main__":
    pip = HeadlessPipeline.from_function(sample_pipeline, cache=False)
    app = InteractivePipeQT(pipeline=pip, name="button_demo", size=None)
    app()
