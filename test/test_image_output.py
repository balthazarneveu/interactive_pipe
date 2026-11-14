"""interactive_pipe.Image as a displayable output: its array is shown, its
title is the cell title unless layout.style sets one."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from interactive_pipe import Image, interactive, layout  # noqa: E402
from interactive_pipe.graphical.display import display_kind, prepare_display  # noqa: E402
from interactive_pipe.graphical.window import InteractivePipeWindow  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

INPUT_IMAGE = np.linspace(0.0, 1.0, 4 * 6 * 3).reshape(4, 6, 3)


@interactive()
def wrap_images(img):
    layout.style("styled", title="From layout.style")
    return Image(img, title="Own title"), Image(img[..., 0], title="Ignored: style wins"), Image(img)


def image_pipeline(img):
    titled, styled, untitled = wrap_images(img)
    return [[titled, styled, untitled]]


@interactive()
def heat_image(img):
    layout.style("heat", colormap="viridis")
    return Image(img[..., 0], title="Heat image")


def heat_image_pipeline(img):
    heat = heat_image(img)
    return [[heat]]


class RecordingWindow(InteractivePipeWindow):
    def __init__(self, pipeline):
        super().__init__(pipeline=pipeline)
        self.cells = {}

    def add_image_placeholder(self, row, col):
        self.image_canvas[row][col] = {}  # type: ignore[index]

    def update_image(self, content, row, col):
        self.cells[(row, col)] = (content, self.get_current_style(row, col)["title"])

    def convert_image(self, img):
        return img


def test_display_kind_and_conversion():
    img = Image(INPUT_IMAGE, title="t")
    assert display_kind(img) == "image"
    assert display_kind(Image(INPUT_IMAGE[0, :, 0])) == "signal"
    np.testing.assert_array_equal(prepare_display(img), INPUT_IMAGE)


def test_window_shows_the_array_with_the_right_titles():
    pipe = HeadlessPipeline.from_function(image_pipeline)
    window = RecordingWindow(pipe)
    window.refresh_display(pipe(INPUT_IMAGE))
    content, title = window.cells[(0, 0)]
    np.testing.assert_array_equal(content, INPUT_IMAGE)
    assert title == "Own title"
    assert window.cells[(0, 1)][1] == "From layout.style"
    assert window.cells[(0, 2)][1] == "untitled"  # no title anywhere: the output name


def test_image_title_follows_the_content_between_runs():
    pipe = HeadlessPipeline.from_function(image_pipeline)
    window = RecordingWindow(pipe)
    window.refresh_display(pipe(INPUT_IMAGE))
    window.refresh_display([[INPUT_IMAGE, INPUT_IMAGE, INPUT_IMAGE]])  # plain arrays now
    assert window.cells[(0, 0)][1] == "titled"


def test_style_without_title_keeps_the_name_as_title():
    pipe = HeadlessPipeline.from_function(heat_image_pipeline)
    window = RecordingWindow(pipe)
    window.refresh_display(pipe(INPUT_IMAGE))
    content, title = window.cells[(0, 0)]
    assert content.shape == (4, 6, 3)  # colormap applied to the Image's 2D array
    assert title == "Heat image"


def test_snapshot_shows_images_and_titles():
    from interactive_pipe.headless.snapshot import result_grid

    pipe = HeadlessPipeline.from_function(image_pipeline)
    grid = result_grid(pipe, pipe(INPUT_IMAGE))
    assert [cell.title for cell in grid[0]] == ["Own title", "From layout.style", "untitled"]
    np.testing.assert_array_equal(grid[0][0].content, INPUT_IMAGE)
    rendered = pipe.snapshot(None)
    assert rendered.ndim == 3


def test_qt_backend_shows_the_image_and_its_title():
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    pipe = HeadlessPipeline.from_function(image_pipeline, inputs=["img"])
    gui = qt_gui.InteractivePipeQT(pipeline=pipe, name="qt image")
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    gui.window.refresh()
    cell = gui.window.image_canvas[0][0]
    assert cell["kind"] == "image"
    assert cell["title"].text() == "Own title"
    assert cell["image"].pixmap().width() == 6
    # the pixel readout reports the Image's float values
    assert cell["image"].array is not None and cell["image"].array.dtype == np.float64
    gui.close()


def test_dpg_backend_shows_the_image():
    dpg_gui = pytest.importorskip("interactive_pipe.graphical.dpg_gui")
    from interactive_pipe.graphical import dpg_backend

    try:
        pipe = HeadlessPipeline.from_function(image_pipeline, inputs=["img"])
        gui = dpg_gui.InteractivePipeDPG(pipeline=pipe, name="dpg image")
        gui.pipeline.inputs = [INPUT_IMAGE.copy()]
        gui.window.refresh()
        cell = gui.window.image_canvas[0][0]
        assert cell["kind"] == "image" and cell["texture"] is not None
        assert cell["full_title"] == "Own title"
    finally:
        dpg_backend.destroy_context()


def test_mpl_backend_shows_the_image():
    mpl_gui = pytest.importorskip("interactive_pipe.graphical.mpl_gui")
    pipe = HeadlessPipeline.from_function(image_pipeline, inputs=["img"])
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipe, name="mpl image")
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    gui.window.refresh()
    cell = gui.window.image_canvas[0][0]
    assert cell["kind"] == "image"
    assert cell["ax"].get_title() == "Own title"
    gui.close()


def test_gradio_backend_shows_the_image(monkeypatch):
    gr = pytest.importorskip("gradio")
    from interactive_pipe.graphical.gradio_gui import InteractivePipeGradio

    monkeypatch.setattr(gr.blocks.Blocks, "launch", lambda self, *a, **k: None, raising=True)
    pipe = HeadlessPipeline.from_function(image_pipeline)
    gui = InteractivePipeGradio(pipeline=pipe, name="gradio image")
    gui(INPUT_IMAGE.copy())
    window = gui.window
    assert window.image_canvas[0][0]["type"] == "image"
    assert window.image_canvas[0][0]["title"] == "Own title"
    converted = window.run_fn(*window.default_values)
    first = converted[0] if isinstance(converted, tuple) else converted
    assert first.dtype == np.uint8 and first.shape == (4, 6, 3)
