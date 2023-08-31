from interactive_pipe.headless.pipeline import HeadlessPipeline
import logging
import numpy as np
from copy import deepcopy

class InteractivePipeGUI():
    def __init__(self, pipeline: HeadlessPipeline = None, controls=[], name="", custom_end=lambda :None, audio=False, **kwargs) -> None:
        self.pipeline = pipeline
        self.custom_end = custom_end
        self.audio = audio
        self.name = name
        if hasattr(pipeline, "controls"):
            controls += pipeline.controls
        self.controls = controls
        self.pipeline.global_params["__app"] = self
        self.pipeline.global_params["__pipeline"] = self.pipeline
        self.init_app(**kwargs)
        
    
    def init_app(self):
        raise NotImplementedError
    
    def run(self):
        raise NotImplementedError
    
    def __call__(self, *args, parameters={}, **kwargs) -> None:
        self.pipeline.parameters = parameters
        self.pipeline.parameters = self.pipeline.parameters_from_keyword_args(**kwargs)
        self.pipeline.inputs = list(args)
        results = self.run()
        return results

class InteractivePipeWindow():
    def __init__(self, *args, style=None, **kwargs) -> None:
        self.image_canvas = None
        if style is not None:
            logging.info("no support for style in Qt backend")

    def add_image_placeholder(self, row, col):
        raise NotImplementedError

    def delete_image_placeholder(self, img_widget):
        raise NotImplementedError
    
    def update_image(self, content, row, col):
        raise NotImplementedError

    def check_image_canvas_changes(self, expected_image_canvas_shape):
        if self.image_canvas is not None:
            current_canvas_shape = (len(self.image_canvas), max([len(image_row) for image_row in self.image_canvas]))
            if current_canvas_shape != expected_image_canvas_shape:
                for row_content in self.image_canvas:
                    for img_widget in row_content:
                        if img_widget is not None:
                            self.delete_image_placeholder(img_widget)
                self.image_canvas = None
                logging.warning("Need to fully re-initialize canvas")
    
    def set_image_canvas(self, image_grid):
        expected_image_canvas_shape  = (len(image_grid), max([len(image_row) for image_row in image_grid]))
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

    def set_images(self, image_grid):
        self.set_image_canvas(image_grid)
        for row, image_row in enumerate(image_grid):
            for col, image_array in enumerate(image_row):
                if image_array is None:
                    continue
                self.update_image(image_array, row, col)

    def refresh_display(self, _out):
        out = deepcopy(_out)
        # In case no canvas has been provided
        if isinstance(out, tuple):
            out = [list(out)]
        ny, nx = len(out), 0
        for idy, img_row in enumerate(out):
            if isinstance(img_row, list):
                for idx, out_img in enumerate(img_row):
                    if out[idy][idx] is not None:
                        out[idy][idx] = self.convert_image(out[idy][idx])
                nx = len(img_row)
            else:
                out[idy] = [self.convert_image(out[idy])]
        logging.info(f"{ny} x {nx} figures")
        self.set_images(out)