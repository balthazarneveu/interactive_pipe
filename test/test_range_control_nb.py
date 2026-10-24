"""RangeControl notebook widget: ipywidgets Int/FloatRangeSlider."""

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

pytest.importorskip("ipywidgets")
nb_gui = pytest.importorskip("interactive_pipe.graphical.nb_gui")

from interactive_pipe import RangeControl, interactive  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

INPUT_IMAGE = np.linspace(0.0, 1.0, 4 * 4, dtype=np.float64).reshape(4, 4)


@interactive(
    nb_window=RangeControl((0.2, 0.8), [0.0, 1.0]),
    nb_bins=RangeControl((2, 5), [0, 10]),
)
def nb_range_clip(img, nb_window=(0.2, 0.8), nb_bins=(2, 5)):
    lo, hi = nb_window
    return np.clip(img, lo, hi)


def nb_range_pipeline(img):
    clipped = nb_range_clip(img)
    return clipped


def test_range_sliders_and_interact_updates(capsys):
    pipeline = HeadlessPipeline.from_function(nb_range_pipeline, inputs=["img"])
    gui = nb_gui.InteractivePipeJupyter(pipeline=pipeline, name="nb range")
    widgets = gui.window.sliders_dict
    assert type(widgets["nb_window"]).__name__ == "FloatRangeSlider"
    assert type(widgets["nb_bins"]).__name__ == "IntRangeSlider"
    assert widgets["nb_window"].value == pytest.approx((0.2, 0.8))
    assert widgets["nb_bins"].value == (2, 5)
    gui(INPUT_IMAGE.copy())
    gui.window._interact_fn(nb_window=(0.3, 0.6), nb_bins=(1, 9))
    assert gui.pipeline.parameters["nb_range_clip"]["nb_window"] == pytest.approx((0.3, 0.6))
    assert gui.pipeline.parameters["nb_range_clip"]["nb_bins"] == (1, 9)
    capsys.readouterr()
