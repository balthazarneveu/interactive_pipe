from interactive_pipe import TextPrompt, interactive, interactive_pipeline
import numpy as np
import argparse

# Color definitions (RGB values normalized to 0-1)
COLOR_DICT = {
    "red": [1.0, 0.0, 0.0],
    "green": [0.0, 1.0, 0.0],
    "blue": [0.0, 0.0, 1.0],
}

COLOR_OPTIONS = list(COLOR_DICT.keys())

# Default color - will be updated from command line
DEFAULT_COLOR = "red"


def generate_colored_image(
    color: str = DEFAULT_COLOR, custom_title: str = None, global_params: dict = None
):
    """Generate a solid colored image based on the selected color"""
    rgb = COLOR_DICT[color]

    # Create a 400x400 image with the selected color
    height, width = 400, 400
    img = np.ones((height, width, 3), dtype=np.float32)
    img[:, :] = rgb
    if (
        custom_title is not None
        and isinstance(custom_title, str)
        and len(custom_title) > 0
    ):
        print(f"Setting custom title: {custom_title}")
        global_params["__output_styles"]["colored_image"] = {"title": custom_title}
    else:
        # Set the title to show the selected color
        global_params["__output_styles"]["colored_image"] = {
            "title": f"Selected Color: {color.upper()}"
        }

    return img


def apply_brightness(img: np.ndarray, brightness: float = 1.0):
    """Apply brightness to the image"""
    img = img * brightness
    return img


def sample_pipeline():
    """Main pipeline function"""
    colored_image = generate_colored_image()
    colored_image = apply_brightness(colored_image)
    return [colored_image]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Color dropdown demo with command-line configuration"
    )
    parser.add_argument(
        "-c",
        "--color",
        type=str,
        nargs="+",
        choices=COLOR_OPTIONS,
        default=["red"],
        help=f"Default color to select (choices: {', '.join(COLOR_OPTIONS)})",
    )
    parser.add_argument(
        "-b",
        "--backend",
        type=str,
        choices=["qt", "gradio", "mpl", "kivy", "textual"],
        default="qt",
        help="Backend to use: qt, gradio, mpl, kivy, or textual (default: qt)",
    )
    args = parser.parse_args()
    interactive(
        # color=(args.color[0], args.color),
        color=("green",),
        custom_title=TextPrompt(
            "Toto",
        ),
    )(generate_colored_image)
    interactive(
        brightness=(0.0, 1.0),
    )(apply_brightness)
    interactive_pipeline(gui=args.backend, cache=True, name="color_demo")(
        sample_pipeline
    )()
