from interactive_pipe.graphical.gui import InteractivePipeGUI, InteractivePipeWindow
import matplotlib.pyplot as plt
from interactive_pipe.core.control import Control
from typing import List
import  logging
from interactive_pipe.graphical.mpl_control import ControlFactory
import numpy as np

class InteractivePipeMatplotlib(InteractivePipeGUI):
    def init_app(self, **kwargs):
        self.window = MainWindow(controls=self.controls, name=self.name, pipeline=self.pipeline, **kwargs)

    
    def run(self):
        assert self.pipeline._PipelineCore__initialized_inputs, "Did you forget to initialize the pipeline inputs?"
        self.window.refresh()
        plt.show()



class MainWindow(InteractivePipeWindow):
    def __init__(self,  controls=[], name="", pipeline=None):
        super().__init__(self)
        self.controls = controls
        self.pipeline = pipeline
        self.fig, self.ax = plt.subplots()
        plt.axis('off')
        self.separation = 0.3
        self.next_slider_position = self.separation  # Starting y-position for the first slider
        self.next_slider_increment = 0.04
        self.init_sliders(self.controls)


    def init_sliders(self, controls: List[Control]):
        self.ctrl = {}
        self.result_label = {}
        control_factory = ControlFactory()
        self.sliders_list = {}
        
        for ctrl in controls:
            slider_name = ctrl.name
            ax_control = self.fig.add_axes([0.25, self.next_slider_position, 0.65, 0.03])
            slider_instance = control_factory.create_control(ctrl, self.update_parameter, ax_control=ax_control)
            slider = slider_instance.create()
            self.sliders_list[slider_name] = slider # needed to keep the object alive
            self.ctrl[slider_name] = ctrl
            self.next_slider_position -= self.next_slider_increment
        plt.subplots_adjust(left=0.05, bottom=self.separation, right=1-0.05)
        # self.refresh()

    def update_parameter(self, idx, value):
        self.ctrl[idx].update(value)
        if self.ctrl[idx]._type == bool or self.ctrl[idx]._type == str:
            self.need_redraw = True
        self.refresh()
    

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
        if not hasattr(self, "need_redraw"):
            self.need_redraw = False
        if self.pipeline is not None:
            out = self.pipeline.run()
            self.refresh_display(out)
        if self.need_redraw:
            plt.draw()
        self.need_redraw = False
    
    def convert_image(self, img):
        return img