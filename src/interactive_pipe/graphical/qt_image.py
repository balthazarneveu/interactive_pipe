"""Display helpers for the Qt GUI backend image grid.

Pure numpy -> QPixmap conversion, the 1D-signal Curve fallback, and the
matplotlib canvas-cell helpers. The cell helpers mutate the canvas cell
dict (window.image_canvas[row][col]) passed to them.
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
    QSize,
    QWidget,
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


_signal_warning_emitted = False


def signal_to_curve(signal_1d: np.ndarray) -> "Curve":
    """Wrap a 1D signal as a Curve so it can at least be displayed (warns once per process)."""
    global _signal_warning_emitted
    if _signal_warning_emitted:
        logging.debug("1D signal displayed as a curve (audio playback not supported)")
    else:
        _signal_warning_emitted = True
        logging.warning(
            "Audio playback not supported with 1D signal"
            + "\nuse live audio instead while using Qt!"
            + "\nuse instead: from interactive_pipe import audio; audio.set(audio_track)"
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


def discard_widget(widget) -> None:
    """Remove `widget` from its layout without it ever reappearing as a window.

    Adding a widget to a layout of a visible window queues a deferred show;
    detaching it with setParent(None) before that event runs would turn it
    into a stray top-level window. An explicit hide() cancels the queued show.
    """
    widget.hide()
    widget.setParent(None)


MPL_CELL_MINIMUM_SIZE = (360, 270)  # pixels, for Curve and Table cells
MPL_CELL_PREFERRED_SIZE = (640, 480)  # pixels: the size a plot asks for (matplotlib's default figure)
# width / height range of a Curve plot: a plot sharing its row with a tall
# image would otherwise be squeezed into a narrow portrait cell, and a plot
# alone in a wide window stretched into a thin band.
PLOT_ASPECT_RANGE = (4.0 / 3.0, 2.0)
TABLE_ASPECT_RANGE = (0.0, float("inf"))  # a table takes its whole cell


def plot_rect(width: int, height: int, aspect_range=PLOT_ASPECT_RANGE):
    """(x, y, w, h) of the largest rectangle of `width` x `height` whose
    width/height lies in `aspect_range`, centered."""
    low, high = aspect_range
    if width <= 0 or height <= 0:
        return 0, 0, max(0, width), max(0, height)
    plot_w, plot_h = width, height
    if width / height > high:
        plot_w = int(round(height * high))
    elif width / height < low:
        plot_h = int(round(width / low))
    return (width - plot_w) // 2, (height - plot_h) // 2, plot_w, plot_h


class PlotFrame(QWidget):
    """Grid cell holding a matplotlib canvas: the frame fills the cell, the
    canvas takes the largest centered part of it within an aspect range.

    The frame asks for a moderate size (``MPL_CELL_PREFERRED_SIZE``): a bare
    canvas asks for its figure size (1000 x 1000 here), which grew the first
    window well beyond what the images needed.
    """

    def __init__(self, canvas, aspect_range=PLOT_ASPECT_RANGE) -> None:
        super().__init__()
        self.canvas = canvas
        self.aspect_range = aspect_range
        canvas.setParent(self)
        canvas.setMinimumSize(1, 1)  # the frame holds the minimum size
        self.setMinimumSize(*MPL_CELL_MINIMUM_SIZE)

    @property
    def figure(self):
        return self.canvas.figure

    def sizeHint(self):  # noqa: N802 - Qt API
        return QSize(*MPL_CELL_PREFERRED_SIZE)

    def minimumSizeHint(self):  # noqa: N802 - Qt API
        return QSize(*MPL_CELL_MINIMUM_SIZE)

    def resizeEvent(self, event):  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self.place_canvas()

    def place_canvas(self) -> None:
        self.canvas.setGeometry(*plot_rect(self.width(), self.height(), self.aspect_range))


def _ensure_mpl_cell(cell: dict, grid_layout, row: int, col: int, aspect_range=PLOT_ASPECT_RANGE):
    """Create the PlotFrame + canvas + axes for a canvas cell once; return the axes."""
    if cell["ax_placeholder"] is None:
        # constrained layout keeps the title and the axis labels inside the cell
        canvas = FigureCanvas(Figure(figsize=(6.4, 4.8), layout="constrained"))
        # A plot stays legible whatever shares its row: without a minimum size the
        # cell shrinks to the height of a small image, or to nothing when the window
        # only holds plots.
        frame = PlotFrame(canvas, aspect_range)
        ax_placeholder = canvas.figure.subplots()
        previous_widget = cell.get("image")
        if previous_widget is not None and previous_widget is not frame:
            detach = getattr(previous_widget, "detach", None)
            if callable(detach):  # an ImageView leaves the shared zoom sync
                detach()
            discard_widget(previous_widget)  # the placeholder view is replaced by the plot
        cell["image"] = frame
        grid_layout.addWidget(frame, 2 * row + 1, col)  # no alignment: the frame fills the cell
        cell["ax_placeholder"] = ax_placeholder
    elif isinstance(cell.get("image"), PlotFrame) and cell["image"].aspect_range != aspect_range:
        cell["image"].aspect_range = aspect_range  # a Curve became a Table (or back)
        cell["image"].place_canvas()
    return cell["ax_placeholder"]


def update_curve_cell(cell: dict, grid_layout, row: int, col: int, curve: "Curve") -> None:
    """Create or update the matplotlib plot for a Curve output in a cell."""
    ax = _ensure_mpl_cell(cell, grid_layout, row, col)
    plt_obj = cell.get("plot_object", None)
    if plt_obj is None:
        cell["plot_object"] = curve.create_plot(ax=ax)  # type: ignore[reportAttributeAccessIssue]
    else:
        cell["plot_object"] = curve.update_plot(plt_obj, ax=ax)  # type: ignore[reportAttributeAccessIssue]
        ax.figure.canvas.draw()


def update_table_cell(cell: dict, grid_layout, row: int, col: int, table: "Table") -> None:
    """Create or update the matplotlib table for a Table output in a cell."""
    ax = _ensure_mpl_cell(cell, grid_layout, row, col, TABLE_ASPECT_RANGE)
    table_obj = cell.get("plot_object", None)
    if table_obj is None:
        cell["plot_object"] = table.create_table(ax=ax)  # type: ignore[reportAttributeAccessIssue]
    else:
        table.update_table(table_obj, ax=ax)  # type: ignore[reportAttributeAccessIssue]
    ax.figure.canvas.draw()
