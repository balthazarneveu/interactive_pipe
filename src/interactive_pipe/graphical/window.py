import logging
import numpy as np
from copy import deepcopy


class InteractivePipeWindow():
    """Display & refresh image results, hosts the sliders & allows refreshing layout grid.

    The window/figure displays the results & the sliders.
    `size = (w, h) | "fullscreen" | "maximized defines"` defines the user expected window size.
    - It deals with the graphical refresh
    - It allows to refreshes the canvas 
    (displaying two images side by side or four images in a 2x2 square fashion for instance.)
    """

    def __init__(self, *args, name=None, pipeline=None, size=None, style=None, **kwargs) -> None:
        self.name = name
        self.image_canvas = None
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
        img_name = self.pipeline.outputs[row][col]
        current_style = self.pipeline.global_params["__output_styles"].get(img_name, {
                                                                           "title": img_name})
        return current_style

    def check_image_canvas_changes(self, expected_image_canvas_shape):
        if self.image_canvas is not None:
            current_canvas_shape = (len(self.image_canvas), max(
                [len(image_row) for image_row in self.image_canvas]))
            if current_canvas_shape != expected_image_canvas_shape:
                for row_content in self.image_canvas:
                    for img_widget in row_content:
                        if img_widget is not None:
                            self.delete_image_placeholder(img_widget)
                self.image_canvas = None
                logging.debug("Need to fully re-initialize canvas")

    def set_image_canvas(self, image_grid):
        expected_image_canvas_shape = (len(image_grid), max(
            [len(image_row) for image_row in image_grid]))
        # Check if the layout has been updated!
        self.check_image_canvas_changes(expected_image_canvas_shape)
        if self.image_canvas is None:
            self.image_canvas = np.empty(expected_image_canvas_shape).tolist()
            for row, image_row in enumerate(image_grid):
                for col, image_array in enumerate(image_row):
                    if image_array is None:
                        self.image_canvas[row][col] = None
                        continue
                    else:
                        self.add_image_placeholder(row, col)

    def set_images(self, image_grid) -> None:
        self.set_image_canvas(image_grid)
        for row, image_row in enumerate(image_grid):
            for col, image_array in enumerate(image_row):
                if image_array is None:
                    continue
                self.update_image(image_array, row, col)

    def refresh_display(self, _out) -> None:
        out = deepcopy(_out)
        # In case no canvas has been provided
        if isinstance(out, tuple):
            out = [list(out)]
        if out is None:
            logging.warning("No output to display")
            return
        ny, nx = len(out), 0
        for idy, img_row in enumerate(out):
            if isinstance(img_row, list):
                for idx, _out_img in enumerate(img_row):
                    if out[idy][idx] is not None:
                        out[idy][idx] = self.convert_image(out[idy][idx])
                nx = len(img_row)
            else:
                out[idy] = [self.convert_image(out[idy])]
        logging.info(f"{ny} x {nx} figures")
        self.set_images(out)
