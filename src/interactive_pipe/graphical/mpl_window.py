import logging
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from interactive_pipe.core.engine import FilterError
from interactive_pipe.data_objects.curves import Curve
from interactive_pipe.data_objects.table import Table
from interactive_pipe.graphical.window import InteractivePipeWindow, display_kind, format_error_message


class MatplotlibWindow(InteractivePipeWindow):
    def __init__(
        self,
        controls=None,
        name="",
        pipeline=None,
        size=None,
        style: Optional[str] = None,
        rc_params=None,
        **unused_kwargs,
    ):
        if controls is None:
            controls = []
        """
        style: dark_background, seaborn-v0_8-dark
        https://matplotlib.org/stable/gallery/style_sheets/style_sheets_reference.html

        rc_params:
        ```
        rc_params = {
            'font.family': 'serif',
            'font.serif': 'Ubuntu',
            'font.size': 10
        }
        """
        super().__init__(size=size, pipeline=pipeline, name=name)
        self.controls = controls
        self.last_error: Optional[FilterError] = None
        self.fig: Optional[Figure] = None  # Will be set by subclasses like MainWindow
        if style is not None:
            plt.style.use(style)
        if rc_params is not None:
            for key, val in rc_params.items():
                plt.rcParams[key] = val

    def add_image_placeholder(self, row, col):
        if self.fig is None:
            raise RuntimeError("Figure not initialized. Subclasses must set self.fig")
        if self.image_canvas is None:
            raise RuntimeError("Image canvas not initialized")
        nrows, ncols = np.array(self.image_canvas).shape
        ax_img = self.fig.add_subplot(nrows, ncols, row * ncols + col + 1)
        self.image_canvas[row][col] = {"ax": ax_img}

    def delete_image_placeholder(self, ax):
        ax["ax"].remove()
        self.need_redraw = True

    def update_style(self, ax: Axes, style: Optional[dict] = None):
        if style is None:
            return
        style = style or {}
        title = style.get("title", None)
        if title:
            ax.set_title(title)
        xlabel = style.get("xlabel", None)
        if xlabel:
            ax.set_xlabel(xlabel)
        ylabel = style.get("ylabel", None)
        if ylabel:
            ax.set_ylabel(ylabel)

    def update_image(self, image_array, row, col):
        if self.image_canvas is None:
            raise RuntimeError("Image canvas not initialized")
        ax_dict = self.image_canvas[row][col]
        ax = ax_dict["ax"]
        img = self.convert_image(image_array)
        if isinstance(img, np.ndarray) and img.ndim == 1:
            img = Curve([img])  # 1D signals are plotted
        kind = display_kind(img)
        if ax_dict.get("kind") != kind:
            # the output type changed since the last frame: start from clean axes
            ax.clear()
            ax_dict["data"] = None
            ax_dict["kind"] = kind
            self.need_redraw = True
        data = ax_dict.get("data")
        if isinstance(img, np.ndarray):
            if data is None:
                ax_dict["data"] = ax.imshow(img)
            else:
                data.set_data(img)
        elif isinstance(img, Curve):
            ax_dict["data"] = img.create_plot(ax=ax) if data is None else img.update_plot(data, ax=ax)
        elif isinstance(img, Table):
            ax_dict["data"] = img.create_table(ax=ax) if data is None else img.update_table(data, ax=ax)
        elif isinstance(img, str):
            if data is None:
                ax_dict["data"] = ax.text(0.5, 0.5, img, ha="center", va="center", fontsize=10)
            else:
                data.set_text(img)
        else:
            logging.warning(f"Unsupported output type for display: {type(img)}")
            return
        curve_has_own_title = isinstance(img, Curve) and img.title is not None
        if not curve_has_own_title and not isinstance(img, Table):
            self.update_style(ax, style=self.get_current_style(row, col))

    def refresh(self):
        if not hasattr(self, "need_redraw"):
            self.need_redraw = False
        if self.pipeline is not None:
            try:
                out = self.pipeline.run()
            except FilterError as error:
                self.show_error(error)
            else:
                self.last_error = None
                self.refresh_display(out)
        if self.need_redraw:
            plt.draw()
        self.need_redraw = False

    def show_error(self, error: FilterError):
        """Draw a pipeline error in red in the failing filter's axes (or the first ones)."""
        self.last_error = error
        for row, col in self.error_cell_positions(error):
            ax_dict = self.image_canvas[row][col]  # type: ignore[index]
            ax = ax_dict["ax"]
            ax.clear()
            ax.set_axis_off()
            ax_dict["data"] = ax.text(
                0.5, 0.5, format_error_message(error), color="red", ha="center", va="center", wrap=True, fontsize=10
            )
            # not a display kind: the next good output starts from clean axes
            ax_dict["kind"] = "error"
        self.need_redraw = True

    def convert_image(self, img):
        if isinstance(img, np.ndarray) and len(img.shape) > 1:
            return img.clip(0.0, 1.0)
        else:
            return img
