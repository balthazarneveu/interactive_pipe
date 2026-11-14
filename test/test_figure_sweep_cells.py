"""Figures in sweeps and snapshots: drawn at the pixel size of their cell
(also inside the sub-figures of a sweep), without a frame, laid out again
at the cell size when the filter called tight_layout(); long single-row
sweep panels are folded into a grid."""

import numpy as np
import pytest
from matplotlib.figure import Figure

from interactive_pipe import Curve, interactive
from interactive_pipe.graphical.display import rasterize_figure
from interactive_pipe.headless import snapshot as snapshot_module
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.headless.snapshot import SnapshotCell, compact_panel

X = np.linspace(0, 6, 50)


def make_figure(tight=False):
    fig = Figure(figsize=(8, 6))
    ax = fig.subplots()
    ax.plot(X, np.sin(X))
    ax.set_xlabel("a long axis label [unit]")
    ax.set_ylabel("amplitude")
    if tight:
        fig.tight_layout()
    return fig


@interactive()
def fig_and_curve(gain=1.0):
    return make_figure(), Curve([gain * np.sin(X)], xlabel="x")


def two_outputs():
    fig, curve = fig_and_curve()
    return fig, curve


def _record_boxes(monkeypatch):
    boxes = []
    real = snapshot_module.rasterize_figure

    def recording(figure, dpi=None, box=None, **kwargs):
        boxes.append((box, dpi))
        return real(figure, dpi, box=box, **kwargs)

    monkeypatch.setattr(snapshot_module, "rasterize_figure", recording)
    return boxes


def test_figure_box_in_a_sweep_is_the_cell_not_the_sheet(monkeypatch):
    boxes = _record_boxes(monkeypatch)
    pipe = HeadlessPipeline.from_function(two_outputs)
    sheet = pipe.sweep(None, gain=[0.5, 1.0, 2.0], output="all")
    assert len(boxes) >= 3
    width_px = sheet.shape[1]
    for box, _ in boxes:
        # each panel holds a figure and a curve side by side: the figure cell is under half the
        # sheet width, and its height under a third of the sheet (three panels)
        assert box[0] / snapshot_module.FIGURE_OVERSAMPLE < width_px / 2
        assert box[1] / snapshot_module.FIGURE_OVERSAMPLE < sheet.shape[0] / 3


def test_figure_text_size_in_a_sweep_matches_a_snapshot(monkeypatch):
    boxes = _record_boxes(monkeypatch)
    pipe = HeadlessPipeline.from_function(two_outputs)
    pipe.snapshot(None)
    (single_box, single_dpi) = boxes[-1]
    pipe.sweep(None, gain=[0.5, 1.0], output="all")
    (sweep_box, sweep_dpi) = boxes[-1]
    # pixels per point, relative to the cell: same text size relative to the cell
    assert single_box[0] / single_dpi == pytest.approx(sweep_box[0] / sweep_dpi, rel=0.15)


def test_figure_cell_has_no_frame_image_cell_keeps_it():
    pipe = HeadlessPipeline.from_function(two_outputs)
    result = pipe()
    grid = snapshot_module.result_grid(pipe, result)
    grid[0].append(SnapshotCell(name="img", content=np.random.default_rng(0).random((8, 8, 3)), title="img"))
    fig = snapshot_module.render_grid(grid)
    figure_ax = [ax for ax in fig.axes if getattr(ax, snapshot_module._FIGURE_CELL, None) is not None]
    assert len(figure_ax) == 1
    assert not any(spine.get_visible() for spine in figure_ax[0].spines.values())
    image_ax = fig.axes[-1]
    assert all(spine.get_visible() for spine in image_ax.spines.values())


def test_tight_layout_figure_is_laid_out_again_at_cell_size():
    tight = make_figure(tight=True)
    margins = dict(vars(tight.subplotpars))
    shrunk = rasterize_figure(tight, box=(300, 300))
    plain = rasterize_figure(make_figure(), box=(300, 300))
    # the same picture as a figure without layout (laid out at the cell size by the library)
    assert np.abs(shrunk - plain).mean() < 0.01
    assert dict(vars(tight.subplotpars)) == margins  # the user's figure is left as it was


def test_bare_subplots_adjust_is_still_kept():
    fig = make_figure()
    fig.subplots_adjust(left=0.3)
    rasterize_figure(fig, box=(300, 300))
    assert fig.subplotpars.left == 0.3
    assert fig.get_layout_engine() is None


def _cells(n):
    return [SnapshotCell(name=f"o{i}", content=np.zeros((4, 8)), title=None) for i in range(n)]


@pytest.mark.parametrize(
    "n, shape",
    [(2, [2]), (3, [3]), (4, [2, 2]), (5, [3, 2]), (6, [3, 3]), (9, [3, 3, 3])],
)
def test_compact_panel_folds_a_long_row(n, shape):
    folded = compact_panel([_cells(n)])
    assert [len(row) for row in folded] == shape
    assert [cell.name for row in folded for cell in row] == [f"o{i}" for i in range(n)]


def test_compact_panel_folds_a_long_column_and_keeps_real_grids():
    column = [[cell] for cell in _cells(4)]
    assert [len(row) for row in compact_panel(column)] == [2, 2]
    cells = _cells(6)
    grid = [cells[:3], cells[3:]]
    assert compact_panel(grid) is grid
