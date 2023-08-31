from interactive_pipe.graphical.gui import InteractivePipeGUI, InteractivePipeWindow
import matplotlib.pyplot as plt
from interactive_pipe.core.control import Control
from typing import List
from interactive_pipe.graphical.nb_control import ControlFactory
import numpy as np
import matplotlib as mpl
from IPython.display import display
from ipywidgets import interact

class InteractivePipeJupyter(InteractivePipeGUI):
    def init_app(self, fullscreen=False, **kwargs):
        self.window = MainWindow(controls=self.controls, name=self.name, pipeline=self.pipeline, **kwargs)

    
    def run(self):
        assert self.pipeline._PipelineCore__initialized_inputs, "Did you forget to initialize the pipeline inputs?"
        interact(self.window._interact_fn, **self.window.sliders_dict)



class MainWindow(InteractivePipeWindow):
    def __init__(self,  controls=[], name="", pipeline=None, style: str=None, rc_params=None):
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
        super().__init__(self)
        self.controls = controls
        self.pipeline = pipeline
        
        if style is not None:
            mpl.style.use(style)
        if rc_params is not None:
            for key, val in rc_params.items():
                plt.rcParams[key] = val
        self.init_sliders(self.controls)

    def create_figure(self):
        if not hasattr(self, "fig"):
            self.fig, self.ax = plt.subplots(figsize=(10, 10))
            plt.axis('off')

    def init_sliders(self, controls: List[Control], dry_run=False):
        self.ctrl = {}
        self.result_label = {}
        control_factory = ControlFactory()
        self.sliders_dict = {}
        
        for ctrl in controls:
            slider_name = ctrl.name
            slider_instance = control_factory.create_control(ctrl)
            slider_widget = slider_instance.create()
            self.sliders_dict[slider_name] = slider_widget # needed to keep the object alive
            self.ctrl[slider_name] = ctrl
        

    def _interact_fn(self, **kwargs):
        for idx, param in kwargs.items():
            self.ctrl[idx].update(param)
        self.refresh()
        # self.fig.canvas.draw()
        display(self.fig)
    

    def add_image_placeholder(self, row, col):
        nrows, ncols = np.array(self.image_canvas).shape
        ax_img = self.fig.add_subplot(nrows, ncols, row * ncols + col + 1)

        self.image_canvas[row][col] = {"ax": ax_img}

    def delete_image_placeholder(self, ax):
        ax["ax"].remove()
        self.need_redraw = True

    def update_image(self, image_array, row, col):
        ax_dict = self.image_canvas[row][col]
        img = self.convert_image(image_array)
        data =  ax_dict.get("data", None)
        if data:
            data.set_data(img)
        else:
            ax_dict["data"] = ax_dict["ax"].imshow(img)


    def refresh(self):
        if self.pipeline is not None:
            out = self.pipeline.run()
            self.create_figure()
            self.refresh_display(out)
    
    def convert_image(self, img):
        return img.clip(0, 1)