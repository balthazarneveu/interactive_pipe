"""Render pipeline results to a PNG: what the GUI would have shown, as a file.

Pure headless: matplotlib's object API (``Figure`` + ``FigureCanvasAgg``) is
used directly, never ``pyplot``, so rendering has no global state, does not
depend on the active matplotlib backend and is safe next to a running Qt /
Dear PyGui window.

The entry points working on a pipeline (``HeadlessPipeline.snapshot`` /
``.sweep``) live in ``interactive_pipe.headless.explore``; this module only
turns results into pictures:

- ``result_grid`` maps a run result onto the output layout (names, titles);
- ``select_cells`` keeps a subset of the cells (``output=``);
- ``render_grid`` draws one grid of cells (``snapshot``);
- ``render_sweep`` draws a grid of grids (``sweep``) with row/column labels;
- ``figure_to_rgb`` / ``save_figure`` export the figure.
"""

import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Collection, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

if TYPE_CHECKING:  # matplotlib is imported when something is rendered
    from matplotlib.figure import Figure

from interactive_pipe.data_objects.curves import Curve
from interactive_pipe.data_objects.table import (
    TABLE_FONTSIZE,  # noqa: F401  (re-exported: snapshot constants)
    TABLE_MAX_ROWS,  # noqa: F401
    TABLE_ROW_HEIGHT,
    Table,
    draw_table,
)
from interactive_pipe.data_objects.table import table_column_widths as _table_column_widths
from interactive_pipe.data_objects.table import table_text as _table_text
from interactive_pipe.graphical.display import (
    TEXT_FONT_PT,
    array_display_problem,
    content_title,
    display_kind,
    figure_of,
    normalize_image,
    prepare_display,
    producer_of,
    rasterize_figure,
    wrap_text,
)
from interactive_pipe.graphical.value_format import format_value  # noqa: F401 - re-exported (describe, explore, check)

# Natural cell sizes in inches (before the whole figure is scaled to fit MAX_WIDTH)
CELL_HEIGHT = 3.2
PLOT_SIZE = (4.4, CELL_HEIGHT)
TEXT_SIZE = (4.4, 1.6)
PLACEHOLDER_SIZE = (3.0, 1.6)
TITLE_HEIGHT = 0.32  # room above each cell for its title
MAX_WIDTH = 22.0  # widest figure (inches) before scaling everything down
MIN_DPI, MAX_DPI = 80, 150
TITLE_FONTSIZE = 10
CAPTION_FONTSIZE = 8

OutputSelector = Union[None, str, int, Sequence[Union[str, int]]]


@dataclass
class SnapshotCell:
    """One displayed output: its content and the title the GUI would show."""

    name: Any
    content: Any
    title: Optional[str]
    raw: Any = None  # the output as the filter returned it (``content`` is converted for display)
    style: Optional[dict] = None  # its layout.style (figures are re-drawn at the cell size)


Grid = List[List[Optional[SnapshotCell]]]


# ---------------------------------------------------------------------------
# Results -> cells
# ---------------------------------------------------------------------------


def _as_rows(structure: Any) -> List[List[Any]]:
    """Flat sequence -> one row; 2D layout -> list of rows; single value -> 1x1."""
    if structure is None:
        return []
    if isinstance(structure, (list, tuple)):
        if any(isinstance(row, (list, tuple)) for row in structure):
            return [list(row) if isinstance(row, (list, tuple)) else [row] for row in structure]
        return [list(structure)]
    return [[structure]]


def output_title(styles: Dict[Any, Dict[str, Any]], name: Any, content: Any = None) -> str:
    """Title shown for an output: its ``layout.style(title=...)``, else the
    title carried by the content (``Image(..., title=...)``), else its name
    (same rule as the GUI windows)."""
    style = styles.get(name) or {}
    if "title" in style:
        return str(style["title"]) if style["title"] is not None else ""
    return content_title(content) or str(name)


def result_grid(pipeline: Any, result: Any) -> Grid:
    """Pair a run result with the pipeline's output names and titles.

    ``result`` is what ``HeadlessPipeline.run()`` returned: a tuple (one row)
    or a 2D list (grid, ``None`` placeholders for empty cells). Names come from
    ``pipeline.outputs`` *after* the run, so a ``layout.grid`` call inside a
    filter is honored, like in the GUI. Each content goes through
    ``prepare_display`` with its ``layout.style``, exactly as in the GUI.
    """
    values = _as_rows(result)
    names = _as_rows(getattr(pipeline, "outputs", None))
    framework_state = getattr(pipeline, "framework_state", None)
    styles = framework_state.output_styles if framework_state is not None else {}
    grid: Grid = []
    for row_idx, row in enumerate(values):
        cells: List[Optional[SnapshotCell]] = []
        for col_idx, content in enumerate(row):
            try:
                name = names[row_idx][col_idx]
            except IndexError:
                name = None
            if name is None and content is None:
                cells.append(None)
                continue
            label = name if name is not None else f"output {row_idx}, {col_idx}"
            # same display conversion as the GUI backends (heatmap colormap, ...)
            shown = prepare_display(
                content, styles.get(label), label, producer_of(getattr(pipeline, "filters", None), name)
            )
            cells.append(
                SnapshotCell(
                    name=label,
                    content=shown,
                    title=output_title(styles, label, content),
                    raw=content,
                    style=styles.get(label),
                )
            )
        grid.append(cells)
    return grid


def flat_cells(grid: Grid) -> List[SnapshotCell]:
    """Non-empty cells in reading order."""
    return [cell for row in grid for cell in row if cell is not None]


def select_cells(grid: Grid, output: OutputSelector) -> Grid:
    """Keep the requested outputs, in the requested order, on one row.

    ``output`` is an output name, an index in reading order (empty cells
    skipped), or a list of them. ``None`` keeps the whole grid. An int that
    is an output name (pipelines routed by buffer indexes) selects that output.
    """
    if output is None:
        return grid
    selectors = [output] if isinstance(output, (str, int)) else list(output)
    if not selectors:
        raise ValueError("output= selects nothing (empty list)")
    cells = flat_cells(grid)
    names = [cell.name for cell in cells]
    chosen: List[Optional[SnapshotCell]] = []
    for selector in selectors:
        if isinstance(selector, bool) or not isinstance(selector, (str, int)):
            raise TypeError(f"output must be an output name, an index or a list of them, got {selector!r}")
        if selector in names:
            chosen.append(cells[names.index(selector)])
        elif isinstance(selector, str):
            if selector not in names:
                raise ValueError(f"No output named {selector!r}, available outputs: {names}")
            chosen.append(cells[names.index(selector)])
        else:
            if not -len(cells) <= selector < len(cells):
                raise IndexError(f"output index {selector} out of range: {len(cells)} outputs {names}")
            chosen.append(cells[selector])
    return [chosen]


def compact_panel(grid: Grid) -> Grid:
    """A sweep panel that is one row or one column of four or more outputs,
    folded into a near-square grid (four outputs: 2 x 2) so that the contact
    sheet stays readable; other layouts are kept."""
    cells = flat_cells(grid)
    single_line = len(grid) == 1 or all(len([cell for cell in row if cell is not None]) <= 1 for row in grid)
    if len(cells) < 4 or not single_line:
        return grid
    ncols = int(np.ceil(np.sqrt(len(cells))))
    return [list(cells[start : start + ncols]) for start in range(0, len(cells), ncols)]


def default_sweep_cell(grid: Grid, changed: Optional[Collection[Any]] = None) -> int:
    """Index (reading order) of the output shown by default in a sweep.

    The only output; else the first image among ``changed`` (the outputs of
    the filters downstream of the swept parameters), else the first of
    ``changed``; else (nothing known to change, e.g. a value passed through
    ``context``) the last image, else the first output. The usual
    ``return img, out`` thus shows ``out``, not the unchanged input."""
    cells = flat_cells(grid)
    if not cells:
        raise ValueError("The pipeline produced no output")
    kinds = [_cell_kind(cell.content) for cell in cells]
    if changed:
        for wanted in ("image", None):
            for index, cell in enumerate(cells):
                if cell.name in changed and (wanted is None or kinds[index] == wanted):
                    return index
    images = [index for index, kind in enumerate(kinds) if kind == "image"]
    return images[-1] if images else 0


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_parameters(parameters: Dict[str, Dict[str, Any]], exclude: Sequence[str] = ()) -> str:
    """One line per filter with parameters: ``filter: a=1, b=0.5``."""
    lines = []
    for filter_name, values in parameters.items():
        items = [f"{key}={format_value(val)}" for key, val in values.items() if key not in exclude]
        if items:
            lines.append(f"{filter_name}: " + ", ".join(items))
    return "\n".join(lines)


def _wrap(text: str, width_inches: float, fontsize: float) -> str:
    """Wrap text to fit approximately `width_inches` at `fontsize` points."""
    max_chars = max(12, int(width_inches * 72.0 / (fontsize * 0.6)))
    lines = []
    for line in text.splitlines() or [""]:
        lines.extend(textwrap.wrap(line, max_chars, subsequent_indent="    ") or [""])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Cell drawing
# ---------------------------------------------------------------------------


def _image_array(content: np.ndarray) -> Optional[np.ndarray]:
    """``(H, W, 3)`` float image in ``[0, 1]`` ready for imshow, None when the
    array is no displayable image. Cells are already through ``prepare_display``;
    this applies the same rules (``array_display_problem`` / ``normalize_image``)
    to anything else."""
    if content.ndim < 2 or array_display_problem(content) is not None:
        return None
    return np.clip(np.nan_to_num(normalize_image(content).astype(np.float32, copy=False)), 0.0, 1.0)


def _cell_kind(content: Any) -> str:
    kind = display_kind(content)
    if kind == "image" and _image_array(content) is None:
        return "unsupported"
    return kind if kind is not None else "unsupported"


def natural_size(content: Any) -> Tuple[float, float]:
    """Natural (width, height) in inches of a cell, before global scaling."""
    kind = _cell_kind(content)
    if kind == "image":
        height, width = content.shape[:2]
        aspect = min(max(width / float(height), 0.33), 3.0)
        # a little extra width: images end up height-bound, no gap above/below
        return CELL_HEIGHT * aspect + 0.15, CELL_HEIGHT
    if kind in ("signal", "curve"):
        return PLOT_SIZE
    if kind == "table":
        header, rows = _table_text(content)
        n_rows = len(rows) + (1 if header else 0)
        widths = _table_column_widths(header, rows)
        return min(max(sum(widths), 2.0), 12.0), max(TABLE_ROW_HEIGHT * n_rows, 0.8)
    if kind == "text":
        n_lines = wrap_text(content, 0.95 * TEXT_SIZE[0] * 72.0, TEXT_FONT_PT).count("\n") + 1
        return TEXT_SIZE[0], max(TEXT_SIZE[1], TEXT_FONT_PT / 72.0 * 1.4 * n_lines + 0.4)
    return PLACEHOLDER_SIZE


def _draw_table(ax: Any, table: Table, height_inches: float) -> None:
    """Table filling its cell, top-aligned (same renderer as the GUI windows)."""
    draw_table(ax, table, height_inches=height_inches - TITLE_HEIGHT)


def _draw_image(ax: Any, content: np.ndarray, pixels_available: float, frame: bool = True) -> None:
    img = _image_array(content)
    if img is None:  # pragma: no cover - filtered out by _cell_kind
        return
    # small images (e.g. 8x8 test patterns): show the pixels, not a blur
    interpolation = "nearest" if img.shape[1] < pixels_available else "antialiased"
    kwargs: Dict[str, Any] = {"interpolation": interpolation}
    ax.imshow(img, **kwargs)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():  # thin frame: shows where a white image ends
        spine.set_color("lightgray")
        spine.set_linewidth(0.6)
        # a figure has its own axes: no frame around it (drawn like a Curve's cell)
        spine.set_visible(frame)


def _set_title(ax: Any, title: Optional[str], width_inches: float) -> None:
    if title:
        ax.set_title(_wrap(title, width_inches, TITLE_FONTSIZE), fontsize=TITLE_FONTSIZE)


def draw_cell(ax: Any, cell: SnapshotCell, width_inches: float, dpi: float, height_inches: float = CELL_HEIGHT) -> None:
    """Draw one output in `ax`, following the GUI conventions."""
    content = cell.content
    kind = _cell_kind(content)
    if kind == "image":
        _draw_image(ax, content, pixels_available=width_inches * dpi, frame=figure_of(cell.raw) is None)
        _set_title(ax, cell.title, width_inches)
        if figure_of(cell.raw) is not None:
            # drawn again at the size of its axes once the layout is known (_redraw_figure_cells)
            setattr(ax, _FIGURE_CELL, (cell.raw, (cell.style or {}).get("dpi")))
    elif kind in ("signal", "curve"):
        curve = Curve([content]) if kind == "signal" else content
        curve.create_plot(ax=ax)
        # like the GUI: a Curve's own title wins over the layout style
        own_title = curve.title if kind == "curve" else None
        _set_title(ax, own_title or cell.title, width_inches)
    elif kind == "table":
        _draw_table(ax, content, height_inches)
        _set_title(ax, content.title or cell.title, width_inches)
    elif kind == "text":
        ax.set_axis_off()
        text = wrap_text(content, 0.95 * width_inches * 72.0, TEXT_FONT_PT)
        ax.text(0.5, 0.5, text, ha="center", va="center", fontsize=TEXT_FONT_PT, transform=ax.transAxes)
        _set_title(ax, cell.title, width_inches)
    else:
        ax.set_axis_off()
        description = type(content).__name__
        if isinstance(content, np.ndarray):
            description = f"ndarray {content.shape} {content.dtype}"
        ax.text(
            0.5,
            0.5,
            f"{description}\n(cannot be displayed)",
            ha="center",
            va="center",
            fontsize=9,
            color="dimgray",
            transform=ax.transAxes,
            bbox={"boxstyle": "round", "facecolor": "whitesmoke", "edgecolor": "lightgray"},
        )
        _set_title(ax, cell.title, width_inches)


# ---------------------------------------------------------------------------
# Grid layout
# ---------------------------------------------------------------------------


def _rectangular(grid: Grid) -> Grid:
    ncols = max((len(row) for row in grid), default=0)
    return [list(row) + [None] * (ncols - len(row)) for row in grid]


def grid_size(grid: Grid) -> Tuple[List[float], List[float]]:
    """Column widths and row heights (inches, titles included) of a grid."""
    grid = _rectangular(grid)
    if not grid or not grid[0]:
        return [PLACEHOLDER_SIZE[0]], [PLACEHOLDER_SIZE[1]]
    ncols = len(grid[0])
    widths = [0.0] * ncols
    heights = [0.0] * len(grid)
    for row_idx, row in enumerate(grid):
        for col_idx, cell in enumerate(row):
            if cell is None:
                continue
            width, height = natural_size(cell.content)
            if figure_of(cell.raw) is not None:  # at least the room of a Curve: same text, same size
                width = max(width, PLOT_SIZE[0])
            widths[col_idx] = max(widths[col_idx], width)
            heights[row_idx] = max(heights[row_idx], height + TITLE_HEIGHT)
    widths = [width if width > 0 else 1.0 for width in widths]
    heights = [height if height > 0 else 1.0 for height in heights]
    return widths, heights


def auto_dpi(cells: Sequence[SnapshotCell], scale: float = 1.0) -> int:
    """Resolution showing the largest image close to its native size (bounded)."""
    dpi = 100.0
    for cell in cells:
        # a figure is drawn at whatever size its cell gets: its raster size does not count
        if _cell_kind(cell.content) == "image" and figure_of(cell.raw) is None:
            dpi = max(dpi, cell.content.shape[0] / (CELL_HEIGHT * scale))
    return int(min(max(dpi, MIN_DPI), MAX_DPI))


_FIGURE_CELL = "_interactive_pipe_figure_cell"
FIGURE_OVERSAMPLE = 2  # figures are drawn twice as large (same layout), then smoothly reduced: no jaggies


def _all_axes(container: Any) -> List[Any]:
    axes = list(container.axes)
    for subfig in getattr(container, "subfigs", []):
        axes += _all_axes(subfig)
    return axes


def _row_neighbours(ax: Any) -> List[Any]:
    """The other axes of the grid sharing a row with `ax` (same gridspec)."""
    spec = ax.get_subplotspec()
    rows = set(spec.rowspan)
    neighbours = []
    for other in spec.get_gridspec().figure.axes:
        other_spec = other.get_subplotspec() if hasattr(other, "get_subplotspec") else None
        if other is ax or other_spec is None or other_spec.get_gridspec() is not spec.get_gridspec():
            continue
        if rows & set(other_spec.rowspan):
            neighbours.append(other)
    return neighbours


def _redraw_figure_cells(fig: "Figure", dpi: float) -> None:
    from matplotlib.transforms import Bbox

    """Draw each matplotlib figure output again at the pixel size of its
    axes, at the snapshot dpi: its text comes out the size of a Curve's in
    the next cell, whatever its figsize (see ``rasterize_figure``)."""
    axes = [ax for ax in _all_axes(fig) if getattr(ax, _FIGURE_CELL, None) is not None]
    if not axes:
        return
    fig.draw_without_rendering()  # runs the (constrained) layout
    renderer = fig.canvas.get_renderer()
    for ax in axes:
        figure, style_dpi = getattr(ax, _FIGURE_CELL)
        # the figure has its own ticks and labels: it also takes the room the
        # layout keeps below the axes of its row for a Curve's tick labels
        extent = ax.get_window_extent(renderer)
        x0, y0, width, height = extent.x0, extent.y0, extent.width, extent.height
        bottom = min([y0] + [other.get_tightbbox(renderer).y0 for other in _row_neighbours(ax)])
        if bottom < y0:
            height, y0 = height + (y0 - bottom), bottom
            container = ax.get_subplotspec().get_gridspec().figure
            ax.set_in_layout(False)  # keep this position when the sheet is drawn
            ax.set_position(container.transSubfigure.inverted().transform_bbox(Bbox.from_bounds(x0, y0, width, height)))
        box = (FIGURE_OVERSAMPLE * width, FIGURE_OVERSAMPLE * height)
        raster = rasterize_figure(figure, FIGURE_OVERSAMPLE * (style_dpi or dpi), box=box)
        for image in list(ax.images):
            image.remove()
        _draw_image(ax, raster, pixels_available=width, frame=False)
        ax.set_anchor("N")  # any spare room goes below the figure, not between it and its title


def draw_grid(container: Any, grid: Grid, scale: float, dpi: float) -> None:
    """Draw a grid of cells in a Figure or SubFigure."""
    grid = _rectangular(grid)
    widths, heights = grid_size(grid)
    if not grid or not grid[0]:
        ax = container.add_subplot(1, 1, 1)
        ax.set_axis_off()
        ax.text(0.5, 0.5, "(no output)", ha="center", va="center", color="dimgray", transform=ax.transAxes)
        return
    gridspec = container.add_gridspec(len(grid), len(grid[0]), width_ratios=widths, height_ratios=heights)
    for row_idx, row in enumerate(grid):
        for col_idx, cell in enumerate(row):
            if cell is None:
                continue
            ax = container.add_subplot(gridspec[row_idx, col_idx])
            draw_cell(ax, cell, widths[col_idx] * scale, dpi, heights[row_idx] * scale)


def _new_figure(width: float, height: float, dpi: float) -> "Figure":
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    fig = Figure(figsize=(width, height), dpi=dpi, layout="constrained")
    FigureCanvasAgg(fig)
    fig.get_layout_engine().set(w_pad=0.06, h_pad=0.06, wspace=0.03, hspace=0.03)  # type: ignore[union-attr]
    return fig


def _decorate(fig: "Figure", width: float, title: Optional[str], caption: Optional[str]) -> None:
    if title:
        fig.suptitle(_wrap(title, width, 13), fontsize=13, fontweight="bold")
    if caption:
        fig.supxlabel(_wrap(caption, width, CAPTION_FONTSIZE), fontsize=CAPTION_FONTSIZE, color="dimgray")


def _extra_height(width: float, title: Optional[str], caption: Optional[str]) -> float:
    extra = 0.0
    if title:
        extra += 0.3 * (_wrap(title, width, 13).count("\n") + 1) + 0.1
    if caption:
        extra += 0.15 * (_wrap(caption, width, CAPTION_FONTSIZE).count("\n") + 1) + 0.05
    return extra


def render_grid(
    grid: Grid,
    *,
    figsize: Optional[Tuple[float, float]] = None,
    dpi: Optional[float] = None,
    title: Optional[str] = None,
    caption: Optional[str] = None,
) -> "Figure":
    """Draw a grid of outputs in a new Figure (sized from the content when
    `figsize` is None)."""
    widths, heights = grid_size(grid)
    natural_width = sum(widths)
    scale = min(1.0, MAX_WIDTH / natural_width)
    if figsize is None:
        width = natural_width * scale
        figsize = (width, sum(heights) * scale + _extra_height(width, title, caption))
    else:
        scale = min(figsize[0] / natural_width, figsize[1] / sum(heights))
    if dpi is None:
        dpi = auto_dpi(flat_cells(grid), scale)
    fig = _new_figure(figsize[0], figsize[1], dpi)
    draw_grid(fig, grid, scale, dpi)
    _decorate(fig, figsize[0], title, caption)
    _redraw_figure_cells(fig, dpi)
    return fig


def render_sweep(
    panels: List[List[Grid]],
    *,
    column_labels: Optional[List[str]] = None,
    row_labels: Optional[List[str]] = None,
    cell_labels: Optional[List[List[str]]] = None,
    figsize: Optional[Tuple[float, float]] = None,
    dpi: Optional[float] = None,
    title: Optional[str] = None,
    caption: Optional[str] = None,
) -> "Figure":
    """Draw a grid of panels (each one a grid of outputs) in a new Figure.

    Labels: `column_labels` above the first row, `row_labels` left of the first
    column, or `cell_labels` above every panel.
    """
    n_rows = len(panels)
    n_cols = max(len(row) for row in panels)
    all_cells = [cell for row in panels for panel in row for cell in flat_cells(panel)]
    panel_w, panel_h = 0.0, 0.0
    for row in panels:
        for panel in row:
            widths, heights = grid_size(panel)
            panel_w, panel_h = max(panel_w, sum(widths)), max(panel_h, sum(heights))
    label_h = 0.3
    row_label_w = 0.35 if row_labels else 0.0
    cell_label_h = label_h if cell_labels is not None else 0.0
    header_h = label_h if column_labels is not None else 0.0
    natural_width = n_cols * panel_w + row_label_w
    natural_height = n_rows * (panel_h + cell_label_h) + header_h
    scale = min(1.0, MAX_WIDTH / natural_width)
    if figsize is None:
        width = natural_width * scale
        figsize = (width, natural_height * scale + _extra_height(width, title, caption))
    else:
        scale = min(figsize[0] / natural_width, figsize[1] / natural_height)
    if dpi is None:
        dpi = auto_dpi(all_cells, scale)
    fig = _new_figure(figsize[0], figsize[1], dpi)
    # Row / column labels get their own header subfigures, so every panel has
    # the same room and the images line up across the sheet.
    row_offset = 1 if column_labels is not None else 0
    col_offset = 1 if row_labels is not None else 0
    subfigs = fig.subfigures(
        n_rows + row_offset,
        n_cols + col_offset,
        squeeze=False,
        wspace=0.01,
        hspace=0.01,
        width_ratios=[row_label_w] * col_offset + [panel_w] * n_cols,
        height_ratios=[header_h] * row_offset + [panel_h + cell_label_h] * n_rows,
    )
    label_style = {"fontsize": 11, "fontweight": "bold", "ha": "center", "va": "center"}
    if column_labels is not None:
        for col_idx, label in enumerate(column_labels):
            subfigs[0][col_idx + col_offset].text(0.5, 0.5, label, **label_style)
    if row_labels is not None:
        for row_idx, label in enumerate(row_labels):
            subfigs[row_idx + row_offset][0].text(0.5, 0.5, label, rotation=90, **label_style)
    for row_idx in range(n_rows):
        for col_idx in range(n_cols):
            if col_idx >= len(panels[row_idx]):
                continue
            subfig = subfigs[row_idx + row_offset][col_idx + col_offset]
            draw_grid(subfig, panels[row_idx][col_idx], scale, dpi)
            if cell_labels is not None and cell_labels[row_idx][col_idx]:
                subfig.suptitle(cell_labels[row_idx][col_idx], fontsize=11, fontweight="bold")
    _decorate(fig, figsize[0], title, caption)
    _redraw_figure_cells(fig, dpi)
    return fig


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def figure_to_rgb(fig: "Figure") -> np.ndarray:
    """Rendered figure as an (H, W, 3) uint8 array."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    canvas = fig.canvas if isinstance(fig.canvas, FigureCanvasAgg) else FigureCanvasAgg(fig)
    canvas.draw()
    return np.asarray(canvas.buffer_rgba())[..., :3].copy()


def save_figure(fig: "Figure", path: Union[str, Path]) -> Path:
    """Write the figure to `path` (PNG unless the suffix says otherwise),
    creating the parent directories."""
    path = Path(path)
    if path.suffix == "":
        path = path.with_suffix(".png")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=fig.dpi, facecolor="white")
    return path
