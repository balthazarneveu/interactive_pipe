from filters_library import switcher
import numpy as np

def test_switcher():
    out = switcher(0, 1, 2, 3, choice=2, amplify=3)
    assert out==(2*3 , 3)

def test_switcher_visually():
    from interactive_pipe import interact
    COLOR_DICT = {
        "red": [0.8, 0., 0.],
        "green": [0., 0.8,0.],
        "blue": [0., 0., 0.8],
        "gray": [0.5, 0.5, 0.5]
    }
    arg_img = [np.array(color_val) * np.ones((64, 64, 3)) 
               for _, color_val in COLOR_DICT.items()]
    r, g, b, w = arg_img
    interact(r, g, b, w, choice=(0, [0, 3]), amplify=[0., 2.])(switcher)
    # you can still run the original function afterward
    # out = switcher(0, 1, 2, 3, choice=2, amplify=3)
    # assert out==(2*3, 3)
