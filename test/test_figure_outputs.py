"""matplotlib Figure / Axes as pipeline outputs: rasterised once with Agg
(graphical.display.prepare_display) for every backend, snapshot, sweep,
save and export_animation; pyplot figures are released (no leak)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from interactive_pipe import TimeControl, interactive, layout  # noqa: E402
from interactive_pipe.data_objects.curves import Curve, SingleCurve  # noqa: E402
from interactive_pipe.graphical.display import (  # noqa: E402
    FIGURE_DPI,
    display_kind,
    prepare_display,
    rasterize_figure,
)
from interactive_pipe.graphical.window import InteractivePipeWindow  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

INPUT_IMAGE = np.linspace(0.0, 1.0, 4 * 4, dtype=np.float64).reshape(4, 4)
RED = (1.0, 0.0, 0.0)


def _has_red(rgb: np.ndarray) -> bool:
    rgb = rgb[..., :3].astype(np.float64)
    if rgb.max() > 1.0:
        rgb = rgb / 255.0
    return bool(((rgb[..., 0] > 0.8) & (rgb[..., 1] < 0.2) & (rgb[..., 2] < 0.2)).any())


# ---------------------------------------------------------------------------
# Filters & pipelines (module level: the AST parser reads the pipeline source)
# ---------------------------------------------------------------------------
@interactive(freq=(2.0, [0.5, 5.0]))
def quiver_figure(img, freq=2.0):
    """Recommended way: matplotlib.figure.Figure, no pyplot state."""
    fig = Figure(figsize=(4, 3))
    ax = fig.subplots()
    y, x = np.mgrid[-1:1:8j, -1:1:8j]
    ax.quiver(x, y, np.cos(freq * y), np.sin(freq * x), color="red")
    return fig


def quiver_pipeline(img):
    fig = quiver_figure(img)
    return fig


@interactive(amp=(1.0, [0.0, 2.0]))
def pyplot_axes(img, amp=1.0):
    """pyplot-made figure returned as its Axes: must not leak."""
    _, ax = plt.subplots(figsize=(3, 2))
    ax.plot(np.arange(5), amp * np.arange(5), color="red", linewidth=4)
    return ax


def pyplot_pipeline(img):
    ax = pyplot_axes(img)
    return ax


@interactive()
def low_dpi_figure(img):
    layout.style("fig", dpi=50, title="Low dpi")
    fig = Figure(figsize=(4, 2))
    fig.subplots().plot([0, 1], color="red")
    return fig


def low_dpi_pipeline(img):
    fig = low_dpi_figure(img)
    return fig


@interactive(fig_kind=("image", ["image", "figure", "text", "curve", "table"]))
def figure_shifter(img, fig_kind="image"):
    from interactive_pipe.data_objects.table import Table

    if fig_kind == "figure":
        fig = Figure(figsize=(2, 2))
        fig.subplots().plot([0, 1], color="red")
        return fig
    if fig_kind == "text":
        return "hello"
    if fig_kind == "curve":
        return Curve([SingleCurve(y=img.mean(axis=0))])
    if fig_kind == "table":
        return Table(img[:2, :2], columns=["a", "b"])
    return img


def figure_shifter_pipeline(img):
    out = figure_shifter(img)
    return out


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------
def test_display_kind_of_figure_axes_and_subfigure():
    fig = Figure()
    ax = fig.subplots()
    sub = fig.subfigures(1, 2)[0]
    assert display_kind(fig) == "figure"
    assert display_kind(ax) == "figure"
    assert display_kind(sub) == "figure"
    assert display_kind(sub.subplots()) == "figure"


def test_figure_is_rasterised_at_the_default_dpi():
    fig = Figure(figsize=(4, 3))
    fig.subplots().plot([0, 1], color="red")
    out = prepare_display(fig)
    assert out.shape == (3 * FIGURE_DPI, 4 * FIGURE_DPI, 3)
    assert out.dtype == np.float32 and 0.0 <= out.min() and out.max() <= 1.0
    assert _has_red(out)
    assert fig.dpi == 100  # the user's figure is left as it was


def test_axes_means_its_figure():
    fig = Figure(figsize=(2, 2))
    ax = fig.subplots()
    np.testing.assert_array_equal(prepare_display(ax), prepare_display(fig))


def test_style_dpi_overrides_the_resolution():
    fig = Figure(figsize=(4, 2))
    assert prepare_display(fig, {"dpi": 50}).shape == (100, 200, 3)


def test_unchanged_figure_is_not_redrawn():
    fig = Figure(figsize=(2, 2))
    ax = fig.subplots()
    ax.plot([0, 1])
    first = rasterize_figure(fig)
    assert rasterize_figure(fig) is first
    ax.plot([1, 0], color="red")  # the figure changed: drawn again
    second = rasterize_figure(fig)
    assert second is not first and _has_red(second)


def test_transparent_figure_is_composited_on_white():
    fig = Figure(figsize=(1, 1))
    fig.patch.set_alpha(0.0)
    out = rasterize_figure(fig, dpi=20)
    np.testing.assert_allclose(out, 1.0)


def test_invalid_dpi_raises():
    with pytest.raises(ValueError):
        rasterize_figure(Figure(), dpi=0)


# ---------------------------------------------------------------------------
# No pyplot leak
# ---------------------------------------------------------------------------
class RecordingWindow(InteractivePipeWindow):
    """Minimal window: records what refresh_display hands to the backend."""

    def __init__(self, pipeline):
        super().__init__(pipeline=pipeline)
        self.cells = {}

    def add_image_placeholder(self, row, col):
        self.image_canvas[row][col] = {}  # type: ignore[index]

    def update_image(self, content, row, col):
        self.cells[(row, col)] = content

    def convert_image(self, img):
        return img


def test_200_gui_refreshes_do_not_grow_pyplot_figures():
    plt.close("all")
    pipe = HeadlessPipeline.from_function(pyplot_pipeline)
    window = RecordingWindow(pipe)
    pipe.inputs = [INPUT_IMAGE.copy()]
    before = list(plt.get_fignums())
    for k in range(200):
        pipe.parameters = {"pyplot_axes": {"amp": k / 100.0}}
        window.refresh_display(pipe.run())
    assert plt.get_fignums() == before
    shown = window.cells[(0, 0)]
    assert shown.ndim == 3 and _has_red(shown)


def test_snapshot_releases_pyplot_figures(tmp_path):
    plt.close("all")
    pipe = HeadlessPipeline.from_function(pyplot_pipeline)
    for amp in (0.5, 1.0, 1.5):
        pipe.snapshot(tmp_path / "s.png", INPUT_IMAGE, amp=amp)
    pipe.sweep(tmp_path / "w.png", INPUT_IMAGE, amp=[0.5, 1.0, 1.5])
    assert plt.get_fignums() == []


# ---------------------------------------------------------------------------
# snapshot / sweep / save / export_animation
# ---------------------------------------------------------------------------
def test_snapshot_and_sweep_show_the_figure():
    pipe = HeadlessPipeline.from_function(quiver_pipeline)
    assert _has_red(pipe.snapshot(None, INPUT_IMAGE))
    assert _has_red(pipe.sweep(None, INPUT_IMAGE, freq=[1.0, 3.0]))


def test_snapshot_uses_the_style_title_and_dpi():
    from interactive_pipe.headless.snapshot import result_grid

    pipe = HeadlessPipeline.from_function(low_dpi_pipeline)
    cell = result_grid(pipe, pipe(INPUT_IMAGE))[0][0]
    assert cell.title == "Low dpi"
    assert cell.content.shape == (100, 200, 3)


def test_save_writes_the_figure(tmp_path):
    from PIL import Image as PILImage

    pipe = HeadlessPipeline.from_function(pyplot_pipeline)
    pipe(INPUT_IMAGE)  # a plain call hands the pyplot figure to the caller: left open
    plt.close("all")
    written = pipe.save(tmp_path / "out.png")  # save runs again and releases its own figure
    pngs = [path for path in written if str(path).endswith(".png")]
    assert len(pngs) == 1
    assert _has_red(np.asarray(PILImage.open(pngs[0]).convert("RGB")))
    assert plt.get_fignums() == []


def test_save_keeps_a_vector_suffix(tmp_path):
    pipe = HeadlessPipeline.from_function(quiver_pipeline)
    pipe(INPUT_IMAGE)
    written = pipe.save(tmp_path / "out.svg")
    assert any(str(path).endswith(".svg") for path in written)


@interactive(t=TimeControl(name="t", update_interval_ms=100))
def time_figure(img, t=0.0):
    fig = Figure(figsize=(2, 1))
    fig.subplots().plot([0, 1], [0, t], color="red")
    return fig


def time_figure_pipeline(img):
    fig = time_figure(img)
    return fig


def test_export_animation_rasterises_figures(tmp_path):
    from PIL import Image as PILImage

    from interactive_pipe import export_animation

    pipe = HeadlessPipeline.from_function(time_figure_pipeline)
    pipe(INPUT_IMAGE)
    path = export_animation(pipe, tmp_path / "anim.gif", duration=0.3, fps=10)
    gif = PILImage.open(path)
    assert gif.n_frames == 3
    assert gif.size == (2 * FIGURE_DPI, FIGURE_DPI)


# ---------------------------------------------------------------------------
# Every backend
# ---------------------------------------------------------------------------
def test_qt_backend_shows_the_figure_and_switches_kinds(monkeypatch):
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    pipe = HeadlessPipeline.from_function(figure_shifter_pipeline, inputs=["img"])
    gui = qt_gui.InteractivePipeQT(pipeline=pipe, name="qt figure")
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    window = gui.window
    # the debounced redraw at the size of the (never shown) view fires or not depending
    # on the machine's load (seen: 200 x 200 instead of 240 x 240): sizes at the view's
    # size are covered by test_figure_text_size, here the figure keeps figsize x FIGURE_DPI
    monkeypatch.setattr(window, "_refit_figure", lambda *_args: None)
    window.refresh()
    for kind in ["figure", "curve", "figure", "text", "figure", "table", "image", "figure"]:
        window.update_parameter("fig_kind", kind)
        qt_gui.QApplication.processEvents()
        cell = window.image_canvas[0][0]
        assert cell["kind"] == ("image" if kind == "figure" else kind)
        if kind == "figure":
            pixmap = cell["image"].pixmap()
            assert (pixmap.width(), pixmap.height()) == (2 * FIGURE_DPI, 2 * FIGURE_DPI)
    gui.close()


def test_dpg_backend_shows_the_figure_and_switches_kinds():
    dpg_gui = pytest.importorskip("interactive_pipe.graphical.dpg_gui")
    from interactive_pipe.graphical import dpg_backend

    try:
        pipe = HeadlessPipeline.from_function(figure_shifter_pipeline, inputs=["img"])
        gui = dpg_gui.InteractivePipeDPG(pipeline=pipe, name="dpg figure")
        gui.pipeline.inputs = [INPUT_IMAGE.copy()]
        window = gui.window
        window.refresh()
        for kind in ["figure", "curve", "figure", "text", "table", "figure", "image"]:
            window.update_parameter("fig_kind", kind)
            window.tick_timers()
            cell = window.image_canvas[0][0]
            expected = "image" if kind == "figure" else kind
            assert cell["kind"] == expected
            assert (cell["texture"] is not None) == (expected == "image")
    finally:
        dpg_backend.destroy_context()


def test_mpl_backend_shows_the_figure_and_switches_kinds():
    mpl_gui = pytest.importorskip("interactive_pipe.graphical.mpl_gui")
    pipe = HeadlessPipeline.from_function(figure_shifter_pipeline, inputs=["img"])
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipe, name="mpl figure")
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    gui.window.refresh()
    for kind in ["figure", "curve", "figure", "text", "figure"]:
        gui.window.update_parameter("fig_kind", kind)
        cell = gui.window.image_canvas[0][0]
        assert cell["kind"] == ("image" if kind == "figure" else kind)
        if kind == "figure":
            assert len(cell["ax"].images) == 1
            # drawn at the size of its axes (square figure: square raster), not at figsize x FIGURE_DPI
            height, width, _ = cell["ax"].images[0].get_array().shape
            assert height == width and height != 2 * FIGURE_DPI
    gui.close()


def test_mpl_backend_rebuilds_the_image_when_its_size_changes():
    """image (4x4) -> figure keeps kind "image": the extent must follow."""
    mpl_gui = pytest.importorskip("interactive_pipe.graphical.mpl_gui")
    pipe = HeadlessPipeline.from_function(figure_shifter_pipeline, inputs=["img"])
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipe, name="mpl resize")
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    gui.window.refresh()
    gui.window.update_parameter("fig_kind", "image")  # controls are shared with the other tests
    ax = gui.window.image_canvas[0][0]["ax"]
    assert ax.images[0].get_extent() == [-0.5, 3.5, 3.5, -0.5]
    gui.window.update_parameter("fig_kind", "figure")
    size = ax.images[0].get_array().shape[0]  # drawn at the size of the axes
    assert size > 4
    assert len(ax.images) == 1
    assert ax.images[0].get_extent() == [-0.5, size - 0.5, size - 0.5, -0.5]
    assert ax.get_title() == "out"
    gui.close()


def test_nb_backend_shows_the_figure():
    nb_gui = pytest.importorskip("interactive_pipe.graphical.nb_gui")
    pipe = HeadlessPipeline.from_function(quiver_pipeline, inputs=["img"])
    gui = nb_gui.InteractivePipeJupyter(pipeline=pipe, name="nb figure")
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    gui.window.refresh()
    cell = gui.window.image_canvas[0][0]
    assert cell["kind"] == "image"
    assert _has_red(np.asarray(cell["ax"].images[0].get_array()))
    plt.close("all")


def test_gradio_backend_shows_the_figure(monkeypatch):
    gr = pytest.importorskip("gradio")
    from interactive_pipe.graphical.gradio_gui import InteractivePipeGradio

    monkeypatch.setattr(gr.blocks.Blocks, "launch", lambda self, *a, **k: None, raising=True)
    pipe = HeadlessPipeline.from_function(quiver_pipeline)
    gui = InteractivePipeGradio(pipeline=pipe, name="gradio figure")
    gui(INPUT_IMAGE.copy())
    window = gui.window
    assert window.image_canvas[0][0]["type"] == "image"
    converted = window.run_fn(*window.default_values)
    assert isinstance(converted, np.ndarray) and converted.dtype == np.uint8
    assert converted.shape == (3 * FIGURE_DPI, 4 * FIGURE_DPI, 3)
    assert _has_red(converted)


def test_qt_worker_rasterises_figures_under_the_run_lock():
    """Threaded Qt: a figure is drawn in the worker (next run may reuse it)."""
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    pipe = HeadlessPipeline.from_function(low_dpi_pipeline, inputs=["img"])
    gui = qt_gui.InteractivePipeQT(pipeline=pipe, name="qt worker")
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    _, out, error, _, _ = gui.window._run_pipeline_in_worker()
    assert error is None
    shown = out
    while isinstance(shown, (tuple, list)):  # the GUI makes the layout 2D
        shown = shown[0]
    assert isinstance(shown, np.ndarray) and shown.shape == (100, 200, 3)  # dpi=50 from layout.style
    gui.close()
