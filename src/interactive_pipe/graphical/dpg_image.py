"""Display helpers for the Dear PyGui image grid.

Each canvas cell is a dict (window.image_canvas[row][col]) holding the Dear
PyGui items of one output: the vertical ``cell`` group, its ``title`` text and
a ``content`` item (image, plot, table or text) plus the raw ``texture`` and
its float32 RGBA ``buffer`` for images. The helpers below mutate that dict.

Images are uploaded as raw float RGBA textures (zero-copy from numpy); curves
use the native plot widget, tables the native table widget.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple, cast

import numpy as np

from interactive_pipe.data_objects.curves import Curve, SingleCurve
from interactive_pipe.data_objects.table import Table
from interactive_pipe.graphical.dpg_backend import dpg

__all__ = [
    "DEFAULT_PLOT_SIZE",
    "DEFAULT_TABLE_SIZE",
    "DEFAULT_TEXT_SIZE",
    "clear_cell_content",
    "numpy_to_rgba",
    "signal_to_curve",
    "update_curve_cell",
    "update_image_cell",
    "update_table_cell",
    "update_text_cell",
]

DEFAULT_PLOT_SIZE = (480, 320)
DEFAULT_TABLE_SIZE = (320, 240)
DEFAULT_TEXT_SIZE = (320, 80)

# matplotlib format-string colors -> RGBA
_FMT_COLORS = {
    "r": (220, 50, 47, 255),
    "g": (60, 180, 75, 255),
    "b": (38, 139, 210, 255),
    "c": (42, 161, 152, 255),
    "m": (211, 54, 130, 255),
    "y": (181, 137, 0, 255),
    "k": (40, 40, 40, 255),
    "w": (240, 240, 240, 255),
}
_MARKER_CHARS = ".,ov^<>12348spP*hH+xXDd|_"
_LINE_PATTERN = re.compile(r"(--|-\.|-|:)")


def numpy_to_rgba(image: np.ndarray) -> np.ndarray:
    """Convert a 2D (grayscale) or 3/4-channel array to a contiguous float32 RGBA array in [0, 1]."""
    if image.ndim == 2:
        gray = image.astype(np.float32, copy=False)
        rgba = np.empty((*gray.shape, 4), dtype=np.float32)
        rgba[..., 0] = gray
        rgba[..., 1] = gray
        rgba[..., 2] = gray
        rgba[..., 3] = 1.0
    elif image.ndim == 3 and image.shape[-1] in (3, 4):
        rgba = np.empty((*image.shape[:2], 4), dtype=np.float32)
        rgba[..., : image.shape[-1]] = image
        if image.shape[-1] == 3:
            rgba[..., 3] = 1.0
    else:
        raise NotImplementedError(f"{image.shape}: only 2D, RGB or RGBA images are supported")
    np.clip(rgba, 0.0, 1.0, out=rgba)
    return np.ascontiguousarray(rgba)


def signal_to_curve(signal_1d: np.ndarray) -> Curve:
    """Wrap a 1D signal as a Curve so it can at least be displayed."""
    logging.warning("Audio playback is not supported by the dpg backend; the 1D signal is displayed as a curve instead")
    return Curve([SingleCurve(y=signal_1d)], ylabel="Amplitude")


def _exists(item) -> bool:
    return item is not None and dpg.does_item_exist(item)


def _delete(item) -> None:
    if _exists(item):
        dpg.delete_item(item)


def clear_cell_content(cell: Dict[str, Any]) -> None:
    """Remove the content item (and texture) of a cell, keeping the group and title."""
    _delete(cell.get("content"))
    _delete(cell.get("texture"))
    for key in ("content", "texture", "buffer", "plot", "kind"):
        cell[key] = None
    cell["natural_size"] = None


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------
def update_image_cell(cell: Dict[str, Any], image: np.ndarray, texture_registry) -> bool:
    """Upload an image into the cell's raw texture; create it on first use or on size change.

    Returns True when the natural size of the cell changed (layout must be recomputed).
    """
    rgba = numpy_to_rgba(image)
    height, width = rgba.shape[:2]
    buffer = cell.get("buffer")
    if buffer is not None and buffer.shape == rgba.shape and _exists(cell.get("texture")):
        np.copyto(buffer, rgba)
        dpg.set_value(cell["texture"], buffer)
        return False
    _delete(cell.get("content"))
    _delete(cell.get("texture"))
    cell["buffer"] = rgba
    cell["texture"] = dpg.add_raw_texture(
        width, height, cast(Any, rgba), format=dpg.mvFormat_Float_rgba, parent=texture_registry
    )
    cell["content"] = dpg.add_image(cell["texture"], parent=cell["cell"], width=width, height=height)
    cell["natural_size"] = (width, height)
    return True


# ---------------------------------------------------------------------------
# Curves
# ---------------------------------------------------------------------------
def _parse_style(style: Optional[str]) -> Tuple[Optional[Tuple[int, int, int, int]], bool, bool]:
    """Split a matplotlib format string into (color, has_line, has_marker)."""
    if not style:
        return None, True, False
    color = None
    for char in style:
        if char in _FMT_COLORS:
            color = _FMT_COLORS[char]
            break
    has_line = _LINE_PATTERN.search(style) is not None
    has_marker = any(char in _MARKER_CHARS for char in style)
    if not has_line and not has_marker:
        has_line = True  # color only: default to a line
    return color, has_line, has_marker


def _series_theme(color: Tuple[int, int, int, int], scatter: bool):
    theme = dpg.add_theme()
    component = dpg.add_theme_component(dpg.mvScatterSeries if scatter else dpg.mvLineSeries, parent=theme)
    if scatter:
        dpg.add_theme_color(dpg.mvPlotCol_MarkerFill, color, category=dpg.mvThemeCat_Plots, parent=component)
        dpg.add_theme_color(dpg.mvPlotCol_MarkerOutline, color, category=dpg.mvThemeCat_Plots, parent=component)
    else:
        dpg.add_theme_color(dpg.mvPlotCol_Line, color, category=dpg.mvThemeCat_Plots, parent=component)
    return theme


def _series_data(single_curve: SingleCurve) -> Tuple[List[float], List[float]]:
    y = np.asarray(single_curve.y, dtype=np.float64).ravel()
    if single_curve.x is None:
        x = np.arange(len(y), dtype=np.float64)
    else:
        x = np.asarray(single_curve.x, dtype=np.float64).ravel()
    return x.tolist(), y.tolist()


def _ensure_plot(cell: Dict[str, Any], curve: Curve) -> Dict[str, Any]:
    plot_state = cell.get("plot")
    if plot_state is not None and _exists(cell.get("content")):
        return plot_state
    _delete(cell.get("content"))
    width, height = DEFAULT_PLOT_SIZE
    plot = dpg.add_plot(parent=cell["cell"], width=width, height=height, no_title=True)
    dpg.add_plot_legend(parent=plot)
    x_axis = dpg.add_plot_axis(dpg.mvXAxis, parent=plot)
    y_axis = dpg.add_plot_axis(dpg.mvYAxis, parent=plot)
    cell["content"] = plot
    cell["natural_size"] = (width, height)
    plot_state = {"plot": plot, "x_axis": x_axis, "y_axis": y_axis, "series": []}
    cell["plot"] = plot_state
    return plot_state


def update_curve_cell(cell: Dict[str, Any], curve: Curve) -> bool:
    """Create or update the native plot of a Curve output. Returns True when the cell was (re)created."""
    created = cell.get("plot") is None or not _exists(cell.get("content"))
    plot_state = _ensure_plot(cell, curve)
    series_items: List[Dict[str, Any]] = plot_state["series"]
    legend = False
    for index, single_curve in enumerate(curve.curves):
        if single_curve.y is None:
            continue
        x_data, y_data = _series_data(single_curve)
        color, has_line, has_marker = _parse_style(single_curve.style)
        scatter = has_marker and not has_line
        label = single_curve.label if single_curve.label is not None else f"curve {index}"
        legend = legend or single_curve.label is not None
        alpha = single_curve.alpha
        if color is not None and alpha is not None:
            color = (*color[:3], int(255 * float(alpha)))
        if index < len(series_items) and series_items[index]["scatter"] == scatter:
            entry = series_items[index]
            dpg.set_value(entry["item"], [x_data, y_data])
            dpg.configure_item(entry["item"], label=label)
        else:
            if index < len(series_items):
                _delete(series_items[index]["item"])
            adder = dpg.add_scatter_series if scatter else dpg.add_line_series
            item = adder(x_data, y_data, label=label, parent=plot_state["y_axis"])
            entry = {"item": item, "scatter": scatter, "color": None}
            if index < len(series_items):
                series_items[index] = entry
            else:
                series_items.append(entry)
        if color is not None and entry["color"] != color:
            dpg.bind_item_theme(entry["item"], _series_theme(color, scatter))
            entry["color"] = color
    for entry in series_items[len(curve.curves) :]:
        _delete(entry["item"])
    del series_items[len(curve.curves) :]

    dpg.configure_item(plot_state["x_axis"], label=curve.xlabel or "", no_gridlines=curve.grid is False)
    dpg.configure_item(plot_state["y_axis"], label=curve.ylabel or "", no_gridlines=curve.grid is False)
    dpg.configure_item(plot_state["plot"], label=curve.title or "", no_title=not curve.title)
    for axis, limits in ((plot_state["x_axis"], curve.xlim), (plot_state["y_axis"], curve.ylim)):
        if limits is not None:
            dpg.set_axis_limits(axis, float(limits[0]), float(limits[1]))
        else:
            dpg.set_axis_limits_auto(axis)
            dpg.fit_axis_data(axis)
    legend_items = dpg.get_item_children(plot_state["plot"], 0) or []
    for legend_item in legend_items:
        dpg.configure_item(legend_item, show=legend)
    return created


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------
def update_table_cell(cell: Dict[str, Any], table: Table) -> bool:
    """Rebuild the native table of a Table output (cheap: tables are small). Returns True when created."""
    created = not _exists(cell.get("content"))
    _delete(cell.get("content"))
    width, height = cell.get("natural_size") or DEFAULT_TABLE_SIZE
    container = dpg.add_child_window(parent=cell["cell"], width=width, height=height, border=True)
    has_headers = any(column != "" for column in table.columns)
    if table.title:
        dpg.add_text(table.title, parent=container)
    table_item = dpg.add_table(
        parent=container,
        header_row=has_headers,
        resizable=True,
        policy=dpg.mvTable_SizingStretchProp,
        borders_innerH=True,
        borders_innerV=True,
        borders_outerH=True,
        borders_outerV=True,
        row_background=True,
    )
    for column in table.columns:
        dpg.add_table_column(label=column if column else " ", parent=table_item)
    for row_values in table._format_values():
        row_item = dpg.add_table_row(parent=table_item)
        for value in row_values:
            dpg.add_text(str(value), parent=row_item)
    cell["content"] = container
    cell["natural_size"] = (width, height)
    return created


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------
def update_text_cell(cell: Dict[str, Any], text: str) -> bool:
    """Show a string output. Returns True when the text item was created."""
    if _exists(cell.get("content")) and cell.get("kind") == "text":
        dpg.set_value(cell["content"], text)
        return False
    _delete(cell.get("content"))
    width, height = DEFAULT_TEXT_SIZE
    cell["content"] = dpg.add_text(text, parent=cell["cell"], wrap=width)
    cell["natural_size"] = (width, height)
    return True
