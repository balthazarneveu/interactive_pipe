"""Display helpers for the Qt GUI backend image grid.

Extracted from MainWindow.update_image (tech-debt item 1): pure numpy ->
QPixmap conversion, the 1D-signal Curve fallback, and the matplotlib
canvas-cell helpers. The cell helpers mutate the passed canvas cell dict
(self.image_canvas[row][col]) exactly like the original inline code did -
the contract is just visible in the signatures now.
"""

import logging
from typing import List, Union, cast

import numpy as np

from interactive_pipe.graphical.qt_backend import (
    MPL_SUPPORT,
    Curve,
    Figure,
    FigureCanvas,
    QImage,
    QPixmap,
    Qt,
    SingleCurve,
    Table,
)

__all__ = ["MPL_SUPPORT", "numpy_to_pixmap", "signal_to_curve", "update_curve_cell", "update_table_cell"]


def numpy_to_pixmap(image_array_original: np.ndarray) -> QPixmap:
    """Convert a 2D (grayscale) or 3-channel uint8 array to a QPixmap."""
    if len(image_array_original.shape) == 2:
        # Consider black & white
        image_array = image_array_original.copy()
        c = 3
        image_array = np.expand_dims(image_array, axis=-1)
        image_array = np.repeat(image_array, c, axis=-1)
    elif len(image_array_original.shape) == 3:
        if not isinstance(image_array_original, np.ndarray):
            raise TypeError(f"Expected numpy array, got {type(image_array_original)}")
        if image_array_original.shape[-1] != 3:
            raise ValueError(f"Expected 3-channel image, got {image_array_original.shape[-1]} channels")
        image_array = image_array_original
    else:
        raise NotImplementedError(
            f"{image_array_original.shape}4 dimensions image or more like burst are not supported"
        )
    h, w, c = image_array.shape
    bytes_per_line = c * w
    # Convert numpy array data to bytes for QImage
    image_bytes = image_array.tobytes()
    image = QImage(image_bytes, w, h, bytes_per_line, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(image)


def signal_to_curve(signal_1d: np.ndarray) -> "Curve":
    """Wrap a 1D signal as a Curve so it can at least be displayed."""
    logging.warning(
        "Audio playback not supported with 1D signal"
        + "\nuse live audio instead while using Qt!"
        + "\nuse instead: context['__set_audio'](audio_track)"
        + "\nSee example here: https://github.com/balthazarneveu/interactive_pipe/blob/master/demo/jukebox.py"
    )
    logging.warning("We'll try to display the audio signal as an image instead")
    return Curve(
        cast(
            List[Union[SingleCurve, list, tuple, dict, np.ndarray]],
            [SingleCurve(y=signal_1d)],
        ),
        ylabel="Amplitude",
    )


def _ensure_mpl_cell(cell: dict, grid_layout, row: int, col: int):
    """Create the FigureCanvas + axes for a canvas cell once; return the axes."""
    if cell["ax_placeholder"] is None:
        canvas = FigureCanvas(Figure(figsize=(10, 10)))
        ax_placeholder = canvas.figure.subplots()
        cell["image"] = canvas
        grid_layout.addWidget(
            canvas,
            2 * row + 1,
            col,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        cell["ax_placeholder"] = ax_placeholder
    return cell["ax_placeholder"]


def update_curve_cell(cell: dict, grid_layout, row: int, col: int, curve: "Curve") -> None:
    """Create or update the matplotlib plot for a Curve output in a cell."""
    ax = _ensure_mpl_cell(cell, grid_layout, row, col)
    plt_obj = cell.get("plot_object", None)
    if plt_obj is None:
        cell["plot_object"] = curve.create_plot(ax=ax)  # type: ignore[reportAttributeAccessIssue]
    else:
        curve.update_plot(plt_obj, ax=ax)  # type: ignore[reportAttributeAccessIssue]
        ax.figure.canvas.draw()


def update_table_cell(cell: dict, grid_layout, row: int, col: int, table: "Table") -> None:
    """Create or update the matplotlib table for a Table output in a cell."""
    ax = _ensure_mpl_cell(cell, grid_layout, row, col)
    table_obj = cell.get("plot_object", None)
    if table_obj is None:
        cell["plot_object"] = table.create_table(ax=ax)  # type: ignore[reportAttributeAccessIssue]
    else:
        table.update_table(table_obj, ax=ax)  # type: ignore[reportAttributeAccessIssue]
    ax.figure.canvas.draw()
