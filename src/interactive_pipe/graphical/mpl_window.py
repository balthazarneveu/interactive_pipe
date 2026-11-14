import logging
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from interactive_pipe.core.engine import FilterError
from interactive_pipe.data_objects.curves import Curve
from interactive_pipe.data_objects.table import Table
from interactive_pipe.graphical.pointer_input import (
    POINT_COLOR,
    REGION_COLOR,
    PointerTargets,
    overlay_items,
)
from interactive_pipe.graphical.window import InteractivePipeWindow, display_kind, format_error_message
from interactive_pipe.headless.pointer import pointer_controls


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
        if isinstance(img, np.ndarray) and data is not None and np.shape(data.get_array()) != img.shape:
            # new image size (e.g. image <-> figure output): set_data would keep the old extent
            ax.clear()
            data = ax_dict["data"] = None
            self.need_redraw = True
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

    # ------------------------------------------------------------------
    # Point / region controls: target cells and overlay

    def refresh_display(self, _out) -> None:
        super().refresh_display(_out)
        self.update_pointer_targets(_out)
        self.draw_pointer_overlays()

    def _cell_styles(self) -> dict:
        styles = {}
        for row, cells in enumerate(self.image_canvas or []):
            for col, cell in enumerate(cells):
                if cell is None:
                    continue
                try:
                    styles[(row, col)] = self.get_current_style(row, col)
                except (IndexError, KeyError, TypeError, RuntimeError):
                    pass
        return styles

    def update_pointer_targets(self, raw_out) -> None:
        """Which cell each point / region control is attached to, for this frame."""
        controls = pointer_controls(getattr(self.pipeline, "controls", None))
        if not controls or self.pipeline is None:
            self.pointer_targets = None
            return
        grid = [list(raw_out)] if isinstance(raw_out, tuple) else raw_out
        self.pointer_targets = PointerTargets(controls, self.pipeline.outputs, grid, self._cell_styles())

    def _shown_shape(self, row: int, col: int):
        cell = (self.image_canvas or [[]])[row][col]
        artist = None if cell is None else cell.get("data")
        if artist is None or not hasattr(artist, "get_array"):
            return None
        return np.shape(artist.get_array())

    def cell_data_size(self, row: int, col: int):
        targets = getattr(self, "pointer_targets", None)
        if targets is None:
            return None
        return targets.data_size((row, col), self._shown_shape(row, col))

    def draw_pointer_overlays(self) -> None:
        """Marker / rectangle of each point / region control over its target image
        (drawn by the window: the filter outputs are left untouched)."""
        from matplotlib import patheffects
        from matplotlib.patches import Rectangle

        outline = [patheffects.withStroke(linewidth=2, foreground="black")]

        targets = getattr(self, "pointer_targets", None)
        for row, cells in enumerate(self.image_canvas or []):
            for col, cell in enumerate(cells):
                if cell is None:
                    continue
                for artist in cell.pop("pointer_artists", []):
                    try:
                        artist.remove()
                    except (ValueError, NotImplementedError, AttributeError):
                        pass  # already gone with an ax.clear()
                if targets is None or cell.get("kind") != "image":
                    continue
                size = self.cell_data_size(row, col)
                if size is None:
                    continue
                ax = cell["ax"]
                artists = []
                point_color = tuple(channel / 255.0 for channel in POINT_COLOR)
                region_color = tuple(channel / 255.0 for channel in REGION_COLOR)
                for kind, coords, label in overlay_items(targets, (row, col), size):
                    if kind == "point":
                        u, v = coords
                        # imshow puts pixel centres on integers: displayed pixel u -> data x = u - 0.5
                        (marker,) = ax.plot(
                            [u - 0.5],
                            [v - 0.5],
                            marker="+",
                            markersize=14,
                            mew=2,
                            color=point_color,
                            scalex=False,
                            scaley=False,
                        )
                        artists.append(marker)
                        artists.append(
                            ax.annotate(
                                label,
                                (u - 0.5, v - 0.5),
                                xytext=(6, 6),
                                textcoords="offset points",
                                color=point_color,
                                fontsize=8,
                                path_effects=outline,
                            )
                        )
                    else:
                        u0, v0, u1, v1 = coords
                        rect = Rectangle(
                            (u0 - 0.5, v0 - 0.5), u1 - u0, v1 - v0, fill=False, edgecolor=region_color, linewidth=1.5
                        )
                        ax.add_patch(rect)
                        artists.append(rect)
                        artists.append(
                            ax.annotate(
                                label,
                                (u0 - 0.5, v0 - 0.5),
                                xytext=(2, 2),
                                textcoords="offset points",
                                color=region_color,
                                fontsize=8,
                                path_effects=outline,
                            )
                        )
                cell["pointer_artists"] = artists
                if artists:
                    self.need_redraw = True

    def show_error(self, error: FilterError):
        """Draw a pipeline error in red in the failing filter's axes (or the first ones)."""
        self.last_error = error
        self.report_error(error)  # on the console too, once
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
