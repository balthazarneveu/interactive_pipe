import logging
from typing import Any, List, Optional

import numpy as np

from interactive_pipe.data_objects.curves import Curve
from interactive_pipe.data_objects.table import Table


def display_kind(content: Any) -> Optional[str]:
    """Classify a pipeline output for display: "image" (2D/3D array), "signal"
    (1D array), "curve", "table", "text" or None when unsupported.

    Backends keep the kind of each canvas cell so that a filter switching
    output type between frames rebuilds the cell instead of feeding the new
    content to the previous widget/artist.
    """
    if isinstance(content, np.ndarray):
        return "signal" if content.ndim == 1 else "image"
    if isinstance(content, Curve):
        return "curve"
    if isinstance(content, Table):
        return "table"
    if isinstance(content, str):
        return "text"
    return None


class InteractivePipeWindow:
    """Display & refresh image results, hosts the sliders & allows refreshing layout grid.

    The window/figure displays the results & the sliders.
    `size = (w, h) | "fullscreen" | "maximized defines"` defines the user expected window size.
    - It deals with the graphical refresh
    - It allows to refreshes the canvas
    (displaying two images side by side or four images in a 2x2 square fashion for instance.)
    """

    def __init__(self, *args, name=None, pipeline=None, size=None, style=None, **kwargs) -> None:
        self.name = name
        self.image_canvas: Optional[List[List[Any]]] = None
        self._size = size
        if style is not None:
            logging.info("no support for style in Qt backend")
        self.pipeline = pipeline

    @property
    def size(self):
        return self._size

    @size.setter
    def size(self, _size):
        self._size = _size

    def add_image_placeholder(self, row, col):
        raise NotImplementedError

    def delete_image_placeholder(self, img_widget):
        raise NotImplementedError

    def update_image(self, content, row, col):
        raise NotImplementedError

    def get_current_style(self, row, col):
        if self.pipeline is None:
            raise RuntimeError("Pipeline is not set")
        img_name = self.pipeline.outputs[row][col]
        current_style = self.pipeline.framework_state.output_styles.get(img_name, {"title": img_name})
        return current_style

    def check_image_canvas_changes(self, expected_image_canvas_shape):
        if self.image_canvas is not None:
            current_canvas_shape = (
                len(self.image_canvas),
                max([len(image_row) for image_row in self.image_canvas]),
            )
            if current_canvas_shape != expected_image_canvas_shape:
                for row_content in self.image_canvas:
                    for img_widget in row_content:
                        if img_widget is not None:
                            self.delete_image_placeholder(img_widget)
                self.image_canvas = None
                logging.debug("Need to fully re-initialize canvas")

    def set_image_canvas(self, image_grid):
        expected_image_canvas_shape = (
            len(image_grid),
            max([len(image_row) for image_row in image_grid]),
        )
        # Check if the layout has been updated!
        self.check_image_canvas_changes(expected_image_canvas_shape)
        if self.image_canvas is None:
            # rectangular canvas: cells of short (jagged) rows and None outputs stay None
            nrows, ncols = expected_image_canvas_shape
            self.image_canvas = [[None] * ncols for _ in range(nrows)]
            for row, image_row in enumerate(image_grid):
                for col, image_array in enumerate(image_row):
                    if image_array is not None:
                        self.add_image_placeholder(row, col)

    def set_images(self, image_grid) -> None:
        self.set_image_canvas(image_grid)
        for row, image_row in enumerate(image_grid):
            for col, image_array in enumerate(image_row):
                if image_array is None:
                    continue
                self.update_image(image_array, row, col)

    def convert_image(self, img):
        """Convert image to backend-specific format. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement convert_image")

    def refresh_display(self, _out) -> None:
        if _out is None:
            logging.warning("No output to display")
            return
        # In case no canvas has been provided
        if isinstance(_out, tuple):
            _out = [list(_out)]
        # Build a fresh grid of converted outputs: the pipeline results are left untouched
        # (no deep copy of the buffers - converting large images every frame is costly enough).
        out = []
        for img_row in _out:
            if isinstance(img_row, list):
                out.append([None if img is None else self.convert_image(img) for img in img_row])
            else:
                out.append([self.convert_image(img_row)])
        logging.debug(f"{len(out)} x {max((len(row) for row in out), default=0)} figures")
        self.set_images(out)
