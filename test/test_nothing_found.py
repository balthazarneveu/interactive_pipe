"""Nothing found must not crash: every ``draw`` function with zero marks
returns the image unchanged, and an empty ``Table`` is shown as its headers
(snapshot and every backend). ``Table`` takes numpy columns, pandas frames,
list of dicts and dict of lists."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from interactive_pipe import draw, interactive  # noqa: E402
from interactive_pipe.data_objects.table import Table, draw_table  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

# function -> keyword arguments of zero marks (positional mark argument second)
EMPTY_MARKS = {
    "points": [np.zeros((0, 2)), []],
    "boxes": [np.zeros((0, 4)), []],
    "lines": [np.zeros((0, 2, 2)), []],
    "polygon": [np.zeros((0, 4, 2)), []],
    "mask": [np.zeros((12, 16), dtype=bool), np.zeros((12, 16), dtype=np.int32), np.zeros((12, 16))],
}
COLORS = [None, [], np.zeros((0, 3)), "red"]
IMAGES = {
    "float_rgb": np.random.default_rng(0).random((12, 16, 3)),
    "uint8_rgb": (np.random.default_rng(1).random((12, 16, 3)) * 255).astype(np.uint8),
    "uint16_rgba": (np.random.default_rng(2).random((12, 16, 4)) * 65535).astype(np.uint16),
}


def _cases():
    for name, marks in EMPTY_MARKS.items():
        for k, mark in enumerate(marks):
            for color in COLORS:
                yield pytest.param(
                    name,
                    mark,
                    color,
                    id=f"{name}-{k}-{color if isinstance(color, str) else len(color) if color is not None else None}",
                )
    for color in COLORS:
        yield pytest.param("text", ([], np.zeros((0, 2))), color, id=f"text-{color!r:.10}")


@pytest.mark.parametrize("image", sorted(IMAGES))
@pytest.mark.parametrize("function, marks, color", list(_cases()))
def test_zero_marks_return_the_image_unchanged(function, marks, color, image):
    img = IMAGES[image]
    if function == "text":
        out = draw.text(img, marks[0], marks[1], color=color)
    elif function == "mask" and color is not None and not isinstance(color, str) and marks.dtype.kind == "f":
        pytest.skip("a soft mask takes a single colour")
    else:
        kwargs = {"color": color}
        if function in ("points", "boxes"):
            kwargs["labels"] = []
        out = getattr(draw, function)(img, marks, **kwargs)
    assert out.dtype == img.dtype
    np.testing.assert_array_equal(out, img)
    assert out is not img


def test_zero_marks_keep_the_grayscale_promotion():
    """Same output shape with and without marks: a display does not jump."""
    gray = np.zeros((8, 8))
    assert draw.boxes(gray, np.zeros((0, 4)), color=[]).shape == (8, 8, 3)
    assert draw.boxes(gray, [[1, 1, 4, 4]]).shape == (8, 8, 3)


def test_an_empty_colour_list_is_still_an_error_with_marks():
    with pytest.raises(ValueError, match="Empty colour list for 2 item"):
        draw.boxes(np.zeros((8, 8, 3)), [[0, 0, 2, 2], [1, 1, 3, 3]], color=[])
    with pytest.raises(ValueError, match="Empty colour list for a mask"):
        draw.mask(np.zeros((8, 8, 3)), np.ones((8, 8), dtype=int), color=[])


# ---------------------------------------------------------------------------
# Table inputs
# ---------------------------------------------------------------------------

TABLE_INPUTS = {
    "dict_of_lists": lambda: {"x": [1, 2], "score": [0.5, 0.25]},
    "dict_of_numpy": lambda: {"x": np.array([1, 2]), "score": np.array([0.5, 0.25], dtype=np.float32)},
    "dict_of_tuples": lambda: {"x": (1, 2), "score": (0.5, 0.25)},
    "list_of_dicts": lambda: [{"x": 1, "score": 0.5}, {"x": np.int64(2), "score": np.float32(0.25)}],
    "pandas": lambda: pytest.importorskip("pandas").DataFrame({"x": [1, 2], "score": [0.5, 0.25]}),
    "pandas_series": lambda: {
        "x": pytest.importorskip("pandas").Series([1, 2]),
        "score": pytest.importorskip("pandas").Series([0.5, 0.25]),
    },
}


@pytest.mark.parametrize("kind", sorted(TABLE_INPUTS))
def test_table_inputs(kind):
    table = Table(TABLE_INPUTS[kind]())
    assert table.columns == ["x", "score"]
    assert table.values == [[1, 0.5], [2, 0.25]]
    # plain Python values: formatting and pickling do not depend on the input type
    assert all(type(value) in (int, float) for row in table.values for value in row)
    assert table._format_values() == [["1", "0.50"], ["2", "0.25"]]


EMPTY_TABLES = {
    "dict_of_empty_lists": lambda: {"x": [], "y": []},
    "dict_of_empty_numpy": lambda: {"x": np.zeros(0), "y": np.arange(0)},
    "numpy_zero_rows": lambda: np.zeros((0, 2)),
    "pandas": lambda: pytest.importorskip("pandas").DataFrame({"x": [], "y": []}),
}


@pytest.mark.parametrize("kind", sorted(EMPTY_TABLES))
def test_empty_table_inputs_keep_their_columns(kind):
    data = EMPTY_TABLES[kind]()
    table = Table(data, columns=["x", "y"]) if isinstance(data, np.ndarray) else Table(data)
    assert table.columns == ["x", "y"]
    assert len(table) == 0


def test_dict_columns_are_validated_with_their_name():
    with pytest.raises(TypeError, match="column 'x' got int"):
        Table({"x": 3})
    with pytest.raises(TypeError, match="column 'x' got str"):
        Table({"x": "abc"})
    with pytest.raises(ValueError, match="Column 'x' must be 1D"):
        Table({"x": np.zeros((2, 2))})
    with pytest.raises(ValueError, match="x: 2, y: 1"):
        Table({"x": [1, 2], "y": [1]})


@pytest.mark.parametrize("table", [Table({"x": [], "y": []}), Table(), Table(np.zeros((0, 3)))])
def test_draw_table_without_rows(table):
    from matplotlib.figure import Figure

    ax = Figure(figsize=(3, 2)).subplots()
    mpl_table = draw_table(ax, table, title="detections")
    texts = [t.get_text() for t in ax.texts]
    if table.columns and any(table.columns):
        assert "(no rows)" in texts
        assert [cell.get_text().get_text() for cell in mpl_table.get_celld().values()] == ["x", "y"]
    elif table.columns:  # headerless: one row of empty cells is not drawn, nothing to show
        assert mpl_table is not None or "(empty table)" in texts
    else:
        assert mpl_table is None and "(empty table)" in texts
    ax.figure.savefig(os.devnull, format="png")  # draws


def test_gui_table_rows_keep_their_height_when_the_window_is_resized():
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figure = Figure(figsize=(4, 10))
    FigureCanvasAgg(figure)
    ax = figure.subplots()
    mpl_table = Table({"x": [1, 2, 3]}).create_table(ax=ax)
    figure.canvas.draw()
    tall = mpl_table._bbox[3]
    figure.set_size_inches(4, 3)
    figure.canvas.draw()
    short = mpl_table._bbox[3]
    # same height in inches: a bigger fraction of a smaller axes
    assert short == pytest.approx(tall * 10 / 3, rel=0.01)


# ---------------------------------------------------------------------------
# An empty table on every backend and in snapshots
# ---------------------------------------------------------------------------

CURRENT = {"table": Table({"x": [], "y": []}, title="detections")}


@interactive()
def detections(img):
    return CURRENT["table"]


def table_pipeline(img):
    out = detections(img)
    return out


IMG = np.zeros((8, 8, 3))


def test_snapshot_of_an_empty_table(tmp_path):
    pipe = HeadlessPipeline.from_function(table_pipeline)
    picture = pipe.snapshot(None, IMG)
    assert picture.ndim == 3


def test_qt_shows_an_empty_table():
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    pipe = HeadlessPipeline.from_function(table_pipeline, inputs=["img"])
    gui = qt_gui.InteractivePipeQT(pipeline=pipe, name="empty table")
    try:
        gui.pipeline.inputs = [IMG]
        gui.window.refresh()
        ax = gui.window.image_canvas[0][0]["ax_placeholder"]
        assert "(no rows)" in [t.get_text() for t in ax.texts]
    finally:
        gui.close()


def test_mpl_shows_an_empty_table():
    mpl_gui = pytest.importorskip("interactive_pipe.graphical.mpl_gui")
    pipe = HeadlessPipeline.from_function(table_pipeline, inputs=["img"])
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipe, name="empty table")
    try:
        gui.pipeline.inputs = [IMG]
        gui.window.refresh()
        gui.window.refresh()  # update path
        ax = gui.window.image_canvas[0][0]["ax"]
        assert [t.get_text() for t in ax.texts].count("(no rows)") == 1
    finally:
        gui.close()


def test_dpg_shows_an_empty_table():
    dpg_gui = pytest.importorskip("interactive_pipe.graphical.dpg_gui")
    import dearpygui.dearpygui as dpg

    from interactive_pipe.graphical import dpg_backend

    try:
        pipe = HeadlessPipeline.from_function(table_pipeline, inputs=["img"])
        gui = dpg_gui.InteractivePipeDPG(pipeline=pipe, name="empty table")
        gui.pipeline.inputs = [IMG]
        gui.window.refresh()
        cell = gui.window.image_canvas[0][0]
        container = cell["content"]
        table_item = [item for item in dpg.get_item_children(container, 1) if dpg.get_item_type(item).endswith("Table")]
        columns = dpg.get_item_children(table_item[0], 0)
        assert [dpg.get_item_label(column) for column in columns] == ["x", "y"]
    finally:
        dpg_backend.destroy_context()


def test_gradio_shows_an_empty_table_with_its_headers(monkeypatch):
    gr = pytest.importorskip("gradio")
    from interactive_pipe.graphical.gradio_gui import InteractivePipeGradio

    monkeypatch.setattr(gr.blocks.Blocks, "launch", lambda self, *a, **k: None, raising=True)
    pipe = HeadlessPipeline.from_function(table_pipeline)
    gui = InteractivePipeGradio(pipeline=pipe, name="empty table")
    gui(IMG)
    value = gui.window.run_fn(*gui.window.default_values)
    value = value[0] if isinstance(value, tuple) else value
    assert value == {"headers": ["x", "y"], "data": []}
    shown = gr.Dataframe().postprocess(value)
    assert list(shown.headers) == ["x", "y"] and shown.data == []
