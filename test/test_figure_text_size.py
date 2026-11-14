"""A matplotlib figure output is drawn at the size of its cell (keeping its
aspect ratio), so its text comes out the size of a Curve's in the next cell
whatever its ``figsize`` (snapshots, Qt, matplotlib and Dear PyGui windows).
Without a known cell size (Gradio, notebook, export) it keeps its figsize."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from interactive_pipe import interactive  # noqa: E402
from interactive_pipe.graphical.display import (  # noqa: E402
    FIGURE_DPI,
    FIGURE_SCREEN_DPI,
    fitted_figure_size,
    prepare_display,
    rasterize_figure,
)
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

X = np.linspace(0, 6, 50)


def make_figure(figsize):
    fig = Figure(figsize=figsize)
    ax = fig.subplots()
    ax.plot(X, np.sin(X))
    ax.set_title("title")
    ax.set_xlabel("time [s]")
    return fig


def test_fitted_size_keeps_the_aspect_ratio():
    assert fitted_figure_size((6.4, 4.8), 100, None) == (6.4, 4.8)
    assert fitted_figure_size((6.4, 4.8), 100, (320, 1000)) == pytest.approx((3.2, 2.4))
    assert fitted_figure_size((4, 4), 100, (800, 300)) == pytest.approx((3.0, 3.0))
    assert fitted_figure_size((4, 4), 100, (20, 20)) == (4, 4)  # cell not laid out yet


def test_without_a_box_the_figsize_is_kept():
    assert rasterize_figure(make_figure((4, 3))).shape == (3 * FIGURE_DPI, 4 * FIGURE_DPI, 3)
    assert prepare_display(make_figure((4, 3))).shape == (3 * FIGURE_DPI, 4 * FIGURE_DPI, 3)


@pytest.mark.parametrize("figsize", [(4, 3), (8, 6), (16, 12)])
def test_in_a_box_the_text_size_does_not_depend_on_figsize(figsize):
    reference = rasterize_figure(make_figure((6.4, 4.8)), box=(400, 400))
    raster = rasterize_figure(make_figure(figsize), box=(400, 400))
    assert raster.shape == reference.shape == (300, 400, 3)
    # same picture: the figure is laid out at the same size in inches
    assert np.abs(raster - reference).mean() < 0.01


def test_box_rendering_matches_the_screen_dpi():
    """In a box, 1 inch of the figure is FIGURE_SCREEN_DPI pixels: a figure
    whose figsize is the box size comes out unchanged."""
    fig = make_figure((4, 3))
    raster = rasterize_figure(fig, box=(4 * FIGURE_SCREEN_DPI, 3 * FIGURE_SCREEN_DPI))
    assert raster.shape == (3 * FIGURE_SCREEN_DPI, 4 * FIGURE_SCREEN_DPI, 3)
    sharp = rasterize_figure(make_figure((4, 3)), box=(400, 300), pixel_ratio=2.0)
    assert sharp.shape == (600, 800, 3)  # HiDPI: same layout, twice the pixels


def test_the_figure_is_left_as_it_was():
    fig = make_figure((8, 6))
    params = dict(vars(fig.subplotpars))
    rasterize_figure(fig, box=(300, 200))
    assert tuple(fig.get_size_inches()) == (8, 6)
    assert dict(vars(fig.subplotpars)) == params
    assert not fig.stale
    # a second call at another size is not served from the cache of the first
    assert rasterize_figure(fig, box=(600, 400)).shape == (400, 533, 3)
    assert rasterize_figure(fig, box=(600, 400)) is rasterize_figure(fig, box=(600, 400))


def test_a_shrunk_figure_keeps_its_axis_labels():
    """Default margins are fractions of the figure: drawn smaller with the
    same text, the xlabel would fall off the bottom without a tight layout."""
    raster = rasterize_figure(make_figure((12, 9)), box=(300, 300))
    dark_rows = np.flatnonzero((raster.mean(axis=(1, 2)) < 0.999) & (raster.min(axis=(1, 2)) < 0.5))
    assert dark_rows.max() < raster.shape[0] - 2  # the bottom text is inside


def test_user_margins_are_kept():
    fig = make_figure((8, 6))
    fig.subplots_adjust(left=0.3)
    rasterize_figure(fig, box=(300, 300))
    assert fig.subplotpars.left == 0.3


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

FIGSIZE = {"value": (6.4, 4.8)}


@interactive()
def plot_figure(x):
    return make_figure(FIGSIZE["value"])


def figure_pipeline(x):
    fig = plot_figure(x)
    return fig


@pytest.mark.parametrize("figsize", [(4, 3), (12, 9)])
def test_snapshot_figure_text_does_not_depend_on_figsize(figsize):
    FIGSIZE["value"] = (6.4, 4.8)
    reference = HeadlessPipeline.from_function(figure_pipeline).snapshot(None, X)
    FIGSIZE["value"] = figsize
    picture = HeadlessPipeline.from_function(figure_pipeline).snapshot(None, X)
    assert picture.shape == reference.shape
    assert np.abs(picture.astype(float) - reference.astype(float)).mean() < 3.0  # out of 255


# ---------------------------------------------------------------------------
# GUI windows
# ---------------------------------------------------------------------------


def _spin(app, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def test_qt_draws_the_figure_at_the_size_of_its_view_and_follows_resizes():
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    from interactive_pipe.graphical.qt_backend import QApplication

    FIGSIZE["value"] = (6.4, 4.8)
    pipe = HeadlessPipeline.from_function(figure_pipeline, inputs=["x"])
    gui = qt_gui.InteractivePipeQT(pipeline=pipe, name="figure box")
    try:
        app = QApplication.instance()
        gui.pipeline.inputs = [X]
        gui.window.show()
        gui.window.refresh()
        for size in [(900, 600), (500, 380)]:
            gui.window.resize(*size)
            _spin(app, 0.5)  # past the resize debounce
            view = gui.window.image_canvas[0][0]["image"]
            pixmap = view.pixmap()
            width, height = view.width(), view.height()
            # fitted in the view, 4:3
            assert abs(pixmap.width() - width) <= 1 or abs(pixmap.height() - height) <= 1
            assert pixmap.width() <= width + 1 and pixmap.height() <= height + 1
            assert abs(pixmap.width() / pixmap.height() - 4 / 3) < 0.02
    finally:
        gui.close()


def test_mpl_draws_the_figure_at_the_size_of_its_axes():
    mpl_gui = pytest.importorskip("interactive_pipe.graphical.mpl_gui")
    FIGSIZE["value"] = (12, 9)
    pipe = HeadlessPipeline.from_function(figure_pipeline, inputs=["x"])
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipe, name="figure box mpl")
    try:
        gui.pipeline.inputs = [X]
        gui.window.refresh()
        ax = gui.window.image_canvas[0][0]["ax"]
        fig = gui.window.fig
        position = ax.get_position(original=True)
        box_w = position.width * fig.get_size_inches()[0] * fig.dpi
        box_h = position.height * fig.get_size_inches()[1] * fig.dpi
        height, width, _ = ax.images[0].get_array().shape
        assert width <= box_w + 1 and height <= box_h + 1
        assert abs(width - box_w) <= 1 or abs(height - box_h) <= 1
    finally:
        FIGSIZE["value"] = (6.4, 4.8)
        gui.close()


def test_dpg_gives_a_figure_the_size_of_a_plot():
    dpg_gui = pytest.importorskip("interactive_pipe.graphical.dpg_gui")
    from interactive_pipe.graphical import dpg_backend
    from interactive_pipe.graphical.dpg_image import DEFAULT_PLOT_SIZE

    FIGSIZE["value"] = (12, 9)
    try:
        pipe = HeadlessPipeline.from_function(figure_pipeline, inputs=["x"])
        gui = dpg_gui.InteractivePipeDPG(pipeline=pipe, name="figure box dpg")
        gui.pipeline.inputs = [X]
        gui.window.refresh()
        width, height = gui.window.image_canvas[0][0]["natural_size"]
        assert height == DEFAULT_PLOT_SIZE[1] and abs(width - DEFAULT_PLOT_SIZE[1] * 4 / 3) <= 1
    finally:
        FIGSIZE["value"] = (6.4, 4.8)
        dpg_backend.destroy_context()


@interactive(width=(1.0, [0.5, 3.0]))
def plot_figure_with_slider(x, width=1.0):
    fig = make_figure((12, 9))
    fig.axes[0].plot(X, np.cos(X) * width)
    return fig


def slider_figure_pipeline(x):
    fig = plot_figure_with_slider(x)
    return fig


def test_qt_threaded_runs_draw_the_figure_at_the_size_of_its_view():
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    from interactive_pipe.graphical.qt_backend import QApplication

    pipe = HeadlessPipeline.from_function(slider_figure_pipeline, inputs=["x"])
    gui = qt_gui.InteractivePipeQT(pipeline=pipe, name="figure box threaded", threaded=True)
    window = gui.window
    try:
        app = QApplication.instance()
        gui.pipeline.inputs = [X]
        window.show()
        window.refresh()
        window.resize(800, 500)
        _spin(app, 0.5)
        window.update_parameter("width", 2.0)  # run in the worker: the figure is rasterised there
        _spin(app, 1.0)
        view = window.image_canvas[0][0]["image"]
        pixmap = view.pixmap()
        assert pixmap.width() <= view.width() + 1 and pixmap.height() <= view.height() + 1
        assert abs(pixmap.width() - view.width()) <= 1 or abs(pixmap.height() - view.height()) <= 1
    finally:
        window.stop_threaded_runs()
        gui.close()
