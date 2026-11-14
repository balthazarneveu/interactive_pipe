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
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from interactive_pipe.data_objects.curves import Curve
from interactive_pipe.data_objects.table import Table
from interactive_pipe.graphical.display import content_title, display_kind, prepare_display, producer_of

# Natural cell sizes in inches (before the whole figure is scaled to fit MAX_WIDTH)
CELL_HEIGHT = 3.2
PLOT_SIZE = (4.4, CELL_HEIGHT)
TEXT_SIZE = (3.6, 1.6)
PLACEHOLDER_SIZE = (3.0, 1.6)
TITLE_HEIGHT = 0.32  # room above each cell for its title
MAX_WIDTH = 22.0  # widest figure (inches) before scaling everything down
MIN_DPI, MAX_DPI = 80, 150
TITLE_FONTSIZE = 10
TABLE_FONTSIZE = 9
TABLE_ROW_HEIGHT = 0.26  # inches per table row
TABLE_MAX_ROWS = 30  # longer tables are truncated (with a "... N more rows" line)
CAPTION_FONTSIZE = 8

OutputSelector = Union[None, str, int, Sequence[Union[str, int]]]


@dataclass
class SnapshotCell:
    """One displayed output: its content and the title the GUI would show."""

    name: Any
    content: Any
    title: Optional[str]
    raw: Any = None  # the output as the filter returned it (``content`` is converted for display)


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
                SnapshotCell(name=label, content=shown, title=output_title(styles, label, content), raw=content)
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


def default_sweep_cell(grid: Grid) -> int:
    """Index (reading order) of the output shown by default in a sweep:
    the only output, else the first image, else the first output."""
    cells = flat_cells(grid)
    if not cells:
        raise ValueError("The pipeline produced no output")
    for index, cell in enumerate(cells):
        if _cell_kind(cell.content) == "image":
            return index
    return 0


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_value(value: Any) -> str:
    """Short human-readable value: 4 significant digits for floats."""
    if isinstance(value, (bool, np.bool_)):
        return str(bool(value))
    if isinstance(value, (float, np.floating)):
        return f"{float(value):.4g}"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, str):
        return value
    if isinstance(value, (tuple, list)):
        inner = ", ".join(format_value(item) for item in value)
        return f"({inner})" if isinstance(value, tuple) else f"[{inner}]"
    if isinstance(value, np.ndarray):
        return f"array{value.shape}"
    text = repr(value)
    return text if len(text) <= 40 else text[:37] + "..."


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
    """Image ready for imshow (HxW or HxWx3/4; uint8 kept, rest clipped to [0, 1]),
    None when the array cannot be shown as an image."""
    img = content
    if img.ndim == 3 and img.shape[-1] == 1:
        img = img[..., 0]
    if img.ndim not in (2, 3) or (img.ndim == 3 and img.shape[-1] not in (3, 4)):
        return None
    if img.size == 0:
        return None
    if img.dtype == np.uint8:
        return img
    if not (np.issubdtype(img.dtype, np.number) or img.dtype == np.bool_):
        return None
    return np.clip(np.nan_to_num(img.astype(np.float32)), 0.0, 1.0)


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
        n_lines = content.count("\n") + 1
        return TEXT_SIZE[0], max(TEXT_SIZE[1], 0.25 * n_lines + 0.4)
    return PLACEHOLDER_SIZE


def _table_text(table: Table) -> Tuple[List[str], List[List[str]]]:
    """Header (empty when the table has none) and formatted rows, truncated
    to TABLE_MAX_ROWS rows."""
    header = [str(col) for col in table.columns]
    if not any(header):
        header = []
    rows = table._format_values()
    n_cols = max([len(header)] + [len(row) for row in rows] + [1])
    rows = [list(row) + [""] * (n_cols - len(row)) for row in rows]
    if len(rows) > TABLE_MAX_ROWS:
        hidden = len(rows) - (TABLE_MAX_ROWS - 1)
        rows = rows[: TABLE_MAX_ROWS - 1] + [[f"... {hidden} more rows"] + [""] * (n_cols - 1)]
    return header, rows


def _table_column_widths(header: List[str], rows: List[List[str]]) -> List[float]:
    """Column widths in inches from the longest text of each column."""
    columns = list(zip(*([header] if header else []), *rows)) if rows else [(name,) for name in header]
    char_width = TABLE_FONTSIZE / 72.0 * 0.62
    widths = []
    for idx, column in enumerate(columns):
        texts = [text for text in column if not (rows and text.startswith("... ") and idx == 0)]
        longest = max((len(text) for text in texts), default=1)
        widths.append(min(longest, 30) * char_width + 0.2)
    return widths or [1.0]


def _draw_table(ax: Any, table: Table, height_inches: float) -> None:
    """Table filling its cell (the GUI's create_table overflows small axes)."""
    ax.set_axis_off()
    header, rows = _table_text(table)
    if not rows and not header:
        ax.text(0.5, 0.5, "(empty table)", ha="center", va="center", color="dimgray", transform=ax.transAxes)
        return
    widths = _table_column_widths(header, rows)
    total = sum(widths)
    natural_height = TABLE_ROW_HEIGHT * (len(rows) + (1 if header else 0))
    fraction = min(1.0, natural_height / max(height_inches - TITLE_HEIGHT, 0.1))
    mpl_table = ax.table(
        cellText=rows or None,
        colLabels=header or None,
        colWidths=[width / total for width in widths],
        cellLoc="center",
        # natural row height, top-aligned: a short table next to a tall image is not stretched
        bbox=[0.0, 1.0 - fraction, 1.0, fraction],
    )
    mpl_table.auto_set_font_size(False)
    mpl_table.set_fontsize(TABLE_FONTSIZE)
    for (row_idx, _), cell in mpl_table.get_celld().items():
        cell.set_linewidth(0.5)
        if header and row_idx == 0:
            cell.set_facecolor("#e8e8e8")
            cell.get_text().set_fontweight("bold")


def _draw_image(ax: Any, content: np.ndarray, pixels_available: float) -> None:
    img = _image_array(content)
    if img is None:  # pragma: no cover - filtered out by _cell_kind
        return
    # small images (e.g. 8x8 test patterns): show the pixels, not a blur
    interpolation = "nearest" if img.shape[1] < pixels_available else "antialiased"
    kwargs: Dict[str, Any] = {"interpolation": interpolation}
    if img.ndim == 2:
        kwargs.update(cmap="gray", vmin=0, vmax=255 if img.dtype == np.uint8 else 1.0)
    ax.imshow(img, **kwargs)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():  # thin frame: shows where a white image ends
        spine.set_color("lightgray")
        spine.set_linewidth(0.6)


def _set_title(ax: Any, title: Optional[str], width_inches: float) -> None:
    if title:
        ax.set_title(_wrap(title, width_inches, TITLE_FONTSIZE), fontsize=TITLE_FONTSIZE)


def draw_cell(ax: Any, cell: SnapshotCell, width_inches: float, dpi: float, height_inches: float = CELL_HEIGHT) -> None:
    """Draw one output in `ax`, following the GUI conventions."""
    content = cell.content
    kind = _cell_kind(content)
    if kind == "image":
        _draw_image(ax, content, pixels_available=width_inches * dpi)
        _set_title(ax, cell.title, width_inches)
    elif kind in ("signal", "curve"):
        curve = Curve([content]) if kind == "signal" else content
        curve.create_plot(ax=ax)
        # like the GUI: a Curve's own title wins over the layout style
        own_title = curve.title if kind == "curve" else None
        _set_title(ax, own_title or cell.title, width_inches)
        ax.tick_params(labelsize=8)
    elif kind == "table":
        _draw_table(ax, content, height_inches)
        _set_title(ax, content.title or cell.title, width_inches)
    elif kind == "text":
        ax.set_axis_off()
        ax.text(0.5, 0.5, content, ha="center", va="center", fontsize=10, wrap=True, transform=ax.transAxes)
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
            widths[col_idx] = max(widths[col_idx], width)
            heights[row_idx] = max(heights[row_idx], height + TITLE_HEIGHT)
    widths = [width if width > 0 else 1.0 for width in widths]
    heights = [height if height > 0 else 1.0 for height in heights]
    return widths, heights


def auto_dpi(cells: Sequence[SnapshotCell], scale: float = 1.0) -> int:
    """Resolution showing the largest image close to its native size (bounded)."""
    dpi = 100.0
    for cell in cells:
        if _cell_kind(cell.content) == "image":
            dpi = max(dpi, cell.content.shape[0] / (CELL_HEIGHT * scale))
    return int(min(max(dpi, MIN_DPI), MAX_DPI))


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


def _new_figure(width: float, height: float, dpi: float) -> Figure:
    fig = Figure(figsize=(width, height), dpi=dpi, layout="constrained")
    FigureCanvasAgg(fig)
    fig.get_layout_engine().set(w_pad=0.06, h_pad=0.06, wspace=0.03, hspace=0.03)  # type: ignore[union-attr]
    return fig


def _decorate(fig: Figure, width: float, title: Optional[str], caption: Optional[str]) -> None:
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
) -> Figure:
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
) -> Figure:
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
    return fig


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def figure_to_rgb(fig: Figure) -> np.ndarray:
    """Rendered figure as an (H, W, 3) uint8 array."""
    canvas = fig.canvas if isinstance(fig.canvas, FigureCanvasAgg) else FigureCanvasAgg(fig)
    canvas.draw()
    return np.asarray(canvas.buffer_rgba())[..., :3].copy()


def save_figure(fig: Figure, path: Union[str, Path]) -> Path:
    """Write the figure to `path` (PNG unless the suffix says otherwise),
    creating the parent directories."""
    path = Path(path)
    if path.suffix == "":
        path = path.with_suffix(".png")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=fig.dpi, facecolor="white")
    return path
