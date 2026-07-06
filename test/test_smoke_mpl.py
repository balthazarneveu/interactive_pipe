"""Matplotlib GUI smoke tests (Agg backend, no window shown).

Cheap coverage for the shared gui.py/window.py base classes: builds the mpl
backend, refreshes once and checks the layout.style title lands on the
axes. Never call gui.run() here (it calls plt.show and blocks).
"""

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

mpl_gui = pytest.importorskip("interactive_pipe.graphical.mpl_gui")

from interactive_pipe import interactive, layout  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

INPUT_IMAGE = np.linspace(0.0, 1.0, 4 * 4, dtype=np.float64).reshape(4, 4)


@interactive(mpl_gain=(0.5, [0.0, 1.0]))
def mpl_adjust(img, mpl_gain=0.5):
    layout.style("adjusted", title="Adjusted!")
    return img * mpl_gain


@interactive()
def mpl_to_rgb(img):
    return np.stack([img, img, img], axis=-1)


def mpl_pipeline(img):
    adjusted = mpl_adjust(img)
    rgb = mpl_to_rgb(img)
    return adjusted, rgb


def test_window_builds_and_refreshes():
    pipeline = HeadlessPipeline.from_function(mpl_pipeline, inputs=["img"])
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipeline, name="mpl smoke")
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    gui.window.refresh()
    canvas = gui.window.image_canvas
    assert len(canvas) == 1 and len(canvas[0]) == 2
    assert canvas[0][0]["data"] is not None
    assert canvas[0][1]["data"] is not None


def test_styled_title_lands_on_axes():
    pipeline = HeadlessPipeline.from_function(mpl_pipeline, inputs=["img"])
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipeline, name="mpl smoke title")
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    gui.window.refresh()
    canvas = gui.window.image_canvas
    # layout.style -> __output_styles -> get_current_style -> ax.set_title
    assert canvas[0][0]["ax"].get_title() == "Adjusted!"
    assert canvas[0][1]["ax"].get_title() == "rgb"  # unstyled falls back to output name
