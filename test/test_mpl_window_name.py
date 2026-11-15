"""Two matplotlib GUIs with the same name: the second replaces the window instead of raising."""

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

mpl_gui = pytest.importorskip("interactive_pipe.graphical.mpl_gui")

from interactive_pipe import interactive  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402


@interactive(same_name_gain=(1.0, [0.0, 2.0]))
def same_name_amplify(img, same_name_gain=1.0):
    return img * same_name_gain


def same_name_pipeline(img):
    out = same_name_amplify(img)
    return [img, out]


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    import matplotlib.pyplot as plt

    plt.close("all")


def test_a_second_window_with_the_same_name_is_built():
    # matplotlib >= 3.10 raises "Figure 'x' already exists" for plt.subplots(num="x") when it is open:
    # a gui="auto" pipeline module loaded twice (tests, scripts/make_gallery.py) or a notebook cell run again
    import matplotlib.pyplot as plt

    guis = []
    for _ in range(2):
        pipeline = HeadlessPipeline.from_function(same_name_pipeline, inputs=["img"])
        gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipeline, name="same window")
        gui.pipeline.inputs = [np.zeros((8, 8, 3))]
        gui.window.refresh()
        guis.append(gui)
    assert guis[1].window.fig is plt.figure("same window")
    assert plt.get_figlabels().count("same window") == 1
