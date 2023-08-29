from interactive_pipe.graphical.gui import InteractivePipeGUI
import matplotlib.pyplot as plt
from interactive_pipe.core.control import Control
from typing import List
import  logging
from interactive_pipe.graphical.mpl_control import ControlFactory


class InteractivePipeMatplotlib(InteractivePipeGUI):
    def init_app(self, **kwargs):
        self.window = MainWindow(controls=self.controls, name=self.name, pipeline=self.pipeline, **kwargs)

    
    def run(self):
       plt.show()



class MainWindow:
    def __init__(self,  controls=[], name="", pipeline=None):
        self.controls = controls
        self.pipeline = pipeline
        self.fig, self.ax = plt.subplots()
        self.image_axes = []
        plt.axis('off')
        self.next_slider_position = 0.4  # Starting y-position for the first slider
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
        self.refresh()

    def update_parameter(self, idx, value):
        self.ctrl[idx].update(value)
        self.refresh()

    def refresh(self):
        if self.pipeline is not None:
            out = self.pipeline.run()
            ny, nx = len(out), 0
            # Clear existing image axes
            for ax in self.image_axes:
                ax.remove()
            self.image_axes = []

            for idy, img_row in enumerate(out):
                if isinstance(img_row, list):
                    for idx, out_img in enumerate(img_row):
                        if out_img is not None:
                            ax_img = self.fig.add_subplot(ny, nx, idy * nx + idx + 1)
                            ax_img.imshow(self.convert_image(out_img))
                            self.image_axes.append(ax_img)
                    nx = len(img_row)
                else:
                    ax_img = self.fig.add_subplot(1, ny, idy + 1)
                    plt.subplots_adjust(left=0.05, bottom=0.4, right=1-0.05)
                    ax_img.imshow(self.convert_image(img_row))
                    self.image_axes.append(ax_img)
            logging.info(f"{ny} x {nx} figures")
            plt.draw()
    
    def convert_image(self, img):
        return img