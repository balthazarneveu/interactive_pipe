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


@interactive()
def grid_reorder(img):
    from interactive_pipe import layout

    layout.grid([["halved"], ["img"]])  # display order differs from the return order
    return img * 0.5


def reorder_pipeline(img):
    halved = grid_reorder(img)
    return img, halved


def test_layout_grid_does_not_change_what_a_call_returns(tmp_path):
    from interactive_pipe import interactive_pipeline

    pipe = interactive_pipeline(gui=None)(reorder_pipeline)
    for _ in range(2):  # the grid is set during the first run: same result after it
        img, halved = pipe(INPUT_IMAGE)
        np.testing.assert_allclose(halved, INPUT_IMAGE * 0.5)
    assert pipe.outputs == [["halved"], ["img"]]  # the display layout follows the grid
    assert pipe.run()[0][0] is pipe.results[0][0]
    img, halved = pipe.headless(INPUT_IMAGE)
    np.testing.assert_allclose(img, INPUT_IMAGE)
    written = pipe.save(tmp_path / "r.png")
    assert sorted(path.stem for path in written) == ["r_halved", "r_img"]
    gui_pipe = interactive_pipeline(gui="mpl")(reorder_pipeline)
    _, halved = gui_pipe.headless(INPUT_IMAGE)
    np.testing.assert_allclose(halved, INPUT_IMAGE * 0.5)
    gui_pipe.pipeline.close()


def test_two_dimensional_return_stays_a_list_of_rows():
    pipe = HeadlessPipeline.from_function(grid_pipeline, inputs=["img"])
    rows = pipe(INPUT_IMAGE)
    assert [len(row) for row in rows] == [2, 1]
