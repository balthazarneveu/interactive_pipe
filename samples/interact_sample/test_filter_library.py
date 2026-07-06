import numpy as np
from filters_library import switcher


def test_switcher():
    out = switcher(0, 1, 2, 3, choice=2, amplify=3)
    assert out == (2 * 3, 3)


def switcher_visual_check():
    """Manual check that pops a GUI: run this file directly, pytest won't collect it"""
    from interactive_pipe import interact

    COLOR_DICT = {
        "red": [0.8, 0.0, 0.0],
        "green": [0.0, 0.8, 0.0],
        "blue": [0.0, 0.0, 0.8],
        "gray": [0.5, 0.5, 0.5],
    }
    arg_img = [np.array(color_val) * np.ones((64, 64, 3)) for _, color_val in COLOR_DICT.items()]
    r, g, b, w = arg_img
    interact(r, g, b, w, choice=(0, [0, 3]), amplify=[0.0, 2.0])(switcher)


if __name__ == "__main__":
    switcher_visual_check()
