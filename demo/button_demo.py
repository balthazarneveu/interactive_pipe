"""Image-button demo: icons act as buttons, the selection is shared through the context"""

import argparse
from pathlib import Path
from typing import Dict, List

import cv2
import numpy as np

from interactive_pipe import Control, Image, context, interactive, interactive_pipeline, layout

root = Path(__file__).parent
img_folder = root / "images"
SELECTION = "selection"

#: button name -> caption shown under the image
CAPTIONS: Dict[str, str] = {
    "elephant": "ELEPHANT",
    "snail": "SNAIL",
    "rabbit": "RABBIT",
    "pause": "...zzzz",
}
ICONS: List[Path] = [img_folder / f"{name}.png" for name in CAPTIONS]


@interactive(selection=Control("elephant", list(CAPTIONS), icons=ICONS))
def selection_choice(selection: str = "elephant") -> None:
    context[SELECTION] = selection


def handle_selection() -> None:
    """React to the user's selection (here: simply log it to the terminal)"""
    selection = context.get(SELECTION, None)
    first_exec = context.get("first_exec", True)
    if not first_exec:
        caption = CAPTIONS[selection]
        print(f"Selected: {selection}")
        print(f"  Caption: {caption}")
    else:
        context["first_exec"] = False


def image_choice() -> np.ndarray:
    selection = context.get(SELECTION, "elephant")
    img = Image.load_image(img_folder / f"{selection}.png")
    max_height = 300  # Raspberry pi with a 7" touchscreen
    h, w, _c = img.shape
    if h > max_height:
        img = cv2.resize(img, (w * max_height // h, max_height))
        h, w, _c = img.shape
    layout.style("img_out", title=CAPTIONS[selection])  # discard auto titling
    return img


def sample_pipeline() -> List[np.ndarray]:
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
        choices=["qt", "dpg", "gradio", "mpl"],
        default="qt",
        help="Backend to use: qt, gradio, or mpl (default: qt)",
    )
    args = parser.parse_args()
    interactive_pipeline(gui=args.backend)(sample_pipeline)()
