"""Notebook (ipywidgets) GUI smoke tests, run outside any kernel.

ipywidgets.interact builds the widgets and calls the render function once
even without a frontend; IPython.display falls back to printing. Covers the
widget factory per control type, the first render, and parameter updates
through the interact callback.
"""

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

nb_gui = pytest.importorskip("interactive_pipe.graphical.nb_gui")

from interactive_pipe import interactive, layout  # noqa: E402
from interactive_pipe.headless.control import Control  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

INPUT_IMAGE = np.linspace(0.0, 1.0, 4 * 4, dtype=np.float64).reshape(4, 4)


@interactive(
    nb_gain=(0.5, [0.0, 1.0]),
    nb_steps=(2, [0, 4]),
    nb_flag=Control(False),
    nb_mode=("mean", ["mean", "max"]),
    nb_label=Control("hello"),
    nb_free=Control(3),
    nb_single=("only", ["only"]),
)
def nb_adjust(
    img, nb_gain=0.5, nb_steps=2, nb_flag=False, nb_mode="mean", nb_label="hello", nb_free=3, nb_single="only"
):
    layout.style("adjusted", title=f"gain={nb_gain:.2f} {nb_label}")
    return img * nb_gain


def nb_pipeline(img):
    adjusted = nb_adjust(img)
    return adjusted


def build_gui():
    pipeline = HeadlessPipeline.from_function(nb_pipeline, inputs=["img"])
    return nb_gui.InteractivePipeJupyter(pipeline=pipeline, name="nb smoke")


def test_widget_per_control_type():
    gui = build_gui()
    widget_types = {name: type(widget).__name__ for name, widget in gui.window.sliders_dict.items()}
    assert widget_types == {
        "nb_gain": "FloatSlider",
        "nb_steps": "IntSlider",
        "nb_flag": "Checkbox",
        "nb_mode": "Dropdown",
        "nb_label": "Text",
        "nb_free": "IntText",
    }
    assert "nb_single" in gui.window.ctrl  # single-choice control: tracked, no widget


def test_first_render_and_interact_updates(capsys):
    gui = build_gui()
    results = gui(INPUT_IMAGE.copy())
    assert results is None  # notebooks display, they do not return arrays
    canvas = gui.window.image_canvas
    assert len(canvas) == 1 and len(canvas[0]) == 1
    assert canvas[0][0]["ax"].get_title() == "gain=0.50 hello"
    np.testing.assert_allclose(gui.pipeline.results[0][0], INPUT_IMAGE * 0.5)
    # the interact callback feeds widget values back into the controls
    gui.window._interact_fn(nb_gain=0.25, nb_label="bye", nb_free=7)
    assert gui.pipeline.parameters["nb_adjust"]["nb_gain"] == pytest.approx(0.25)
    assert gui.pipeline.parameters["nb_adjust"]["nb_free"] == 7
    assert canvas[0][0]["ax"].get_title() == "gain=0.25 bye"
    capsys.readouterr()  # swallow the text fallback of IPython.display
