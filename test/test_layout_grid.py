"""2D output layouts: None placeholders, jagged rows and layout changes."""

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402

from interactive_pipe import interactive  # noqa: E402
from interactive_pipe.graphical.mpl_gui import InteractivePipeMatplotlib  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

INPUT_IMAGE = np.linspace(0.0, 1.0, 4 * 4, dtype=np.float64).reshape(4, 4)


@interactive(grid_gain=(0.5, [0.0, 1.0]))
def grid_scale(img, grid_gain=0.5):
    return img * grid_gain


@interactive()
def grid_invert(img):
    return 1.0 - img


def grid_pipeline(img):
    scaled = grid_scale(img)
    inverted = grid_invert(img)
    return [[scaled, inverted], [inverted]]


def test_headless_grid_keeps_none_placeholders_aligned():
    pipeline = HeadlessPipeline.from_function(grid_pipeline, inputs=["img"])
    pipeline.outputs = [["scaled", None], ["inverted"]]
    pipeline.inputs = [INPUT_IMAGE.copy()]
    results = pipeline.run()
    assert len(results) == 2
    assert len(results[0]) == 2 and results[0][1] is None
    np.testing.assert_allclose(results[0][0], INPUT_IMAGE * 0.5)
    assert len(results[1]) == 1
    np.testing.assert_allclose(results[1][0], 1.0 - INPUT_IMAGE)


def test_mpl_jagged_grid_survives_layout_change():
    pipeline = HeadlessPipeline.from_function(grid_pipeline, inputs=["img"])
    gui = InteractivePipeMatplotlib(pipeline=pipeline, name="grid smoke")
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    gui.window.refresh()
    canvas = gui.window.image_canvas
    assert len(canvas) == 2 and len(canvas[0]) == 2
    # padding cell of the short second row is an empty placeholder, not garbage
    assert canvas[1][1] is None
    # shrinking the layout must dispose of the previous placeholders cleanly
    gui.pipeline.outputs = [["inverted"]]
    gui.window.refresh()
    canvas = gui.window.image_canvas
    assert len(canvas) == 1 and len(canvas[0]) == 1
    assert canvas[0][0]["ax"].get_title() == "inverted"
    gui.close()
