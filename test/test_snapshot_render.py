"""Snapshot renderer (headless/snapshot.py): run results -> one PNG."""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PIL import Image as PILImage  # noqa: E402

from interactive_pipe.core.framework_state import FrameworkState  # noqa: E402
from interactive_pipe.data_objects.curves import Curve  # noqa: E402
from interactive_pipe.data_objects.table import Table  # noqa: E402
from interactive_pipe.headless.snapshot import (  # noqa: E402
    TABLE_MAX_ROWS,
    SnapshotCell,
    _table_text,
    default_sweep_cell,
    figure_to_rgb,
    format_parameters,
    format_value,
    render_grid,
    render_sweep,
    result_grid,
    save_figure,
    select_cells,
)


class FakePipeline:
    def __init__(self, outputs, styles=None):
        self.outputs = outputs
        self.framework_state = FrameworkState()
        self.framework_state.output_styles.update(styles or {})


def gray(value, shape=(40, 60)):
    return np.full(shape, value, dtype=np.float32)


def cells(*contents):
    return [[SnapshotCell(name=f"c{idx}", content=content, title=f"c{idx}") for idx, content in enumerate(contents)]]


# ---------------------------------------------------------------------------
# result_grid / select_cells
# ---------------------------------------------------------------------------


def test_result_grid_flat_tuple_is_one_row_with_style_titles():
    pipe = FakePipeline(["img", "curve"], styles={"img": {"title": "My image"}})
    grid = result_grid(pipe, (gray(0.5), Curve([np.arange(3)])))
    assert len(grid) == 1 and len(grid[0]) == 2
    assert grid[0][0].title == "My image"
    assert grid[0][1].title == "curve"  # no style: the variable name


def test_result_grid_2d_keeps_empty_cells():
    pipe = FakePipeline([["a", "b"], ["c", None]])
    grid = result_grid(pipe, [[gray(0.1), gray(0.2)], [gray(0.3), None]])
    assert [len(row) for row in grid] == [2, 2]
    assert grid[1][1] is None
    assert grid[1][0].name == "c"


def test_result_grid_style_without_title_falls_back_to_name():
    pipe = FakePipeline(["img"], styles={"img": {"colormap": "viridis"}})
    assert result_grid(pipe, (gray(0.5),))[0][0].title == "img"


def test_select_cells_by_name_index_and_list():
    pipe = FakePipeline([["a", "b"], ["c", None]])
    grid = result_grid(pipe, [[gray(0.1), gray(0.2)], [gray(0.3), None]])
    assert [cell.name for cell in select_cells(grid, "c")[0]] == ["c"]
    assert [cell.name for cell in select_cells(grid, 1)[0]] == ["b"]
    assert [cell.name for cell in select_cells(grid, ["c", 0])[0]] == ["c", "a"]
    assert select_cells(grid, None) is grid
    with pytest.raises(ValueError, match="available outputs"):
        select_cells(grid, "nope")
    with pytest.raises(IndexError):
        select_cells(grid, 3)
    with pytest.raises(TypeError):
        select_cells(grid, [1.5])


def test_default_sweep_cell_prefers_changed_image_then_last_image():
    grid = cells(Curve([np.arange(3)]), "text", gray(0.5), gray(0.2))
    assert default_sweep_cell(grid) == 3  # nothing known to change: the last image
    names = [cell.name for row in grid for cell in row]
    assert default_sweep_cell(grid, {names[2]}) == 2
    assert default_sweep_cell(grid, {names[1], names[3]}) == 3  # images first
    assert default_sweep_cell(grid, {names[1]}) == 1  # no changed image: the first changed output
    assert default_sweep_cell(cells("only text")) == 0


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------


def test_render_grid_proportions_follow_the_layout():
    one_row = figure_to_rgb(render_grid(cells(gray(0.2), gray(0.8), gray(0.5)), caption=None))
    one_col = figure_to_rgb(render_grid([[cell] for cell in cells(gray(0.2), gray(0.8), gray(0.5))[0]], caption=None))
    assert one_row.shape[1] > 2 * one_row.shape[0]
    assert one_col.shape[0] > 2 * one_col.shape[1]


def test_render_is_not_blank_and_cells_differ():
    rgb = figure_to_rgb(render_grid(cells(gray(0.0, (50, 50)), gray(1.0, (50, 50))), caption=None))
    assert rgb.dtype == np.uint8 and rgb.ndim == 3 and rgb.shape[2] == 3
    left, right = rgb[:, : rgb.shape[1] // 2], rgb[:, rgb.shape[1] // 2 :]
    assert left.mean() < right.mean() - 50  # black image on the left, white on the right


def test_every_kind_renders_and_unsupported_is_a_placeholder():
    contents = (
        gray(0.5),
        (np.random.rand(20, 30, 3) * 255).astype(np.uint8),
        np.random.rand(10, 10, 1),
        np.sin(np.linspace(0, 6, 50)),
        Curve([[np.arange(4), np.arange(4) ** 2, "r-", "square"]], title="own title"),
        Table({"a": [1, 2], "b": [0.5, 0.25]}),
        "some text",
        {"not": "displayable"},
        np.zeros((2, 3, 4, 5)),
    )
    fig = render_grid(cells(*contents), title="All kinds", caption="a=1")
    rgb = figure_to_rgb(fig)
    assert rgb.std() > 0
    texts = [text.get_text() for ax in fig.axes for text in ax.texts]
    assert any("cannot be displayed" in text and "dict" in text for text in texts)
    assert any("ndarray (2, 3, 4, 5)" in text for text in texts)
    titles = [ax.get_title() for ax in fig.axes]
    assert "own title" in titles  # a Curve's own title wins, like in the GUI


def test_rendering_does_not_touch_pyplot_state():
    before = plt.get_fignums()
    figure_to_rgb(render_grid(cells(gray(0.5), Curve([np.arange(3)]), Table({"a": [1]}))))
    assert plt.get_fignums() == before


def test_long_tables_are_truncated():
    table = Table({"x": list(range(100))})
    header, rows = _table_text(table)
    assert header == ["x"]
    assert len(rows) == TABLE_MAX_ROWS
    assert rows[-1][0].startswith("... 71 more rows")


def test_explicit_figsize_and_dpi():
    fig = render_grid(cells(gray(0.5)), figsize=(4, 3), dpi=50)
    assert figure_to_rgb(fig).shape[:2] == (150, 200)


def test_save_figure_creates_folders_and_png(tmp_path):
    path = save_figure(render_grid(cells(gray(0.5))), tmp_path / "deep" / "folder" / "out")
    assert path.suffix == ".png" and path.is_file()
    with PILImage.open(path) as img:
        assert img.format == "PNG"


def test_render_sweep_labels():
    panels = [[cells(gray(0.1)), cells(gray(0.9))], [cells(gray(0.3)), cells(gray(0.6))]]
    fig = render_sweep(panels, row_labels=["a=1", "a=2"], column_labels=["b=1", "b=2"])
    rgb = figure_to_rgb(fig)
    assert rgb.std() > 0
    labels = [text.get_text() for subfig in fig.subfigs for text in subfig.texts]
    assert sorted(labels) == ["a=1", "a=2", "b=1", "b=2"]


# ---------------------------------------------------------------------------
# formatting
# ---------------------------------------------------------------------------


def test_format_helpers():
    assert format_value(np.float32(0.123456)) == "0.1235"
    assert format_value((0.2, 0.8)) == "(0.2, 0.8)"
    assert format_value(np.int64(3)) == "3"
    assert format_value(np.zeros((2, 3))) == "array(2, 3)"
    text = format_parameters({"f": {"a": 1, "b": 0.5}, "g": {}, "h": {"c": "x"}}, exclude=["b"])
    assert text == "f: a=1\nh: c=x"


def test_int_names_of_index_routed_pipelines_win_over_positions():
    pipe = FakePipeline([1, 2, 3])
    grid = result_grid(pipe, ("text", gray(0.5), gray(0.1)))
    assert [cell.name for cell in select_cells(grid, 2)[0]] == [2]
    assert [cell.name for cell in select_cells(grid, 0)[0]] == [1]  # not a name: reading order
    assert default_sweep_cell(grid) == 2
    assert default_sweep_cell(grid, {2}) == 1
