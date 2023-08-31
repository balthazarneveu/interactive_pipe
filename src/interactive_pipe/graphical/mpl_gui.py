from interactive_pipe.graphical.gui import InteractivePipeGUI, InteractivePipeWindow
import matplotlib.pyplot as plt
from interactive_pipe.core.control import Control
from typing import List
import  logging
from interactive_pipe.graphical.mpl_control import ControlFactory
from interactive_pipe.graphical.mpl_window import MatplotlibWindow

class InteractivePipeMatplotlib(InteractivePipeGUI):
    def init_app(self, fullscreen=False, **kwargs):
        self.fullscreen = fullscreen
        self.window = MainWindow(controls=self.controls, name=self.name, pipeline=self.pipeline, **kwargs)

    
    def run(self):
        assert self.pipeline._PipelineCore__initialized_inputs, "Did you forget to initialize the pipeline inputs?"
        self.window.refresh()
        if self.fullscreen:
            try:
                mng = plt.get_current_fig_manager()
                mng.full_screen_toggle()
            except Exception as exc:
                print(exc)
                logging.warning("Cannot maximize screen")

        plt.show()



class MainWindow(MatplotlibWindow):
    def __init__(self,  controls=[], name="", pipeline=None, style: str=None, rc_params=None):
        super().__init__(controls=controls, name=name, pipeline=pipeline, style=style, rc_params=rc_params)
        self.fig, self.ax = plt.subplots()
        plt.axis('off')
        self.init_sliders()
        plt.subplots_adjust(left=0.04, top=1, bottom=self.top_of_sliders + 2*self.spacer, right=1-0.04)
    
    def init_sliders(self):
        # Compute the space needed for slider (dry_run) -> go down
        self.spacer = 0.005
        self.footer_space = 0.01
        self.next_slider_position = self.next_button_position = 0
        self.__init_sliders(self.controls, dry_run=True)
        # Then go back up.
        self.next_slider_position *= -1
        self.next_button_position *= -1
        # Then go through the slider and create dedicated figures & widgets
        self.top_of_sliders = max(self.next_slider_position,  self.next_button_position)
        self.__init_sliders(self.controls)
        

    def __init_sliders(self, controls: List[Control], dry_run=False):
        if not dry_run:
            self.ctrl = {}
            self.result_label = {}
            control_factory = ControlFactory()
            self.sliders_list = {}
        
        for ctrl in controls:
            slider_name = ctrl.name
            if ctrl._type == bool or ctrl._type == str:
                x_start = 0.01
                width = 0.08
                number_of_items = (1 if ctrl._type == bool else len(ctrl.value_range))
                height = 0.02 * number_of_items
                y_start = self.next_slider_position - height
                self.next_slider_position -= self.spacer + height
            elif ctrl._type == float or ctrl._type == int:
                x_start = 0.25
                width = 0.65
                height = 0.02
                y_start = self.next_button_position - height
                self.next_button_position -= self.spacer + height
            if not dry_run:
                ax_control = self.fig.add_axes([x_start, y_start, width, height])
                if ctrl._type == bool:
                    ax_control.xaxis.set_visible(True)
                slider_instance = control_factory.create_control(ctrl, self.update_parameter, ax_control=ax_control)
                slider = slider_instance.create()
                self.sliders_list[slider_name] = slider # needed to keep the object alive
                self.ctrl[slider_name] = ctrl
        self.next_slider_position -= self.footer_space
        self.next_button_position -= self.footer_space

    def update_parameter(self, idx, value):
        self.ctrl[idx].update(value)
        if self.ctrl[idx]._type == bool or self.ctrl[idx]._type == str:
            self.need_redraw = True
        self.refresh()

    def refresh(self):
        if not hasattr(self, "need_redraw"):
            self.need_redraw = False
        if self.pipeline is not None:
            out = self.pipeline.run()
            self.refresh_display(out)
        if self.need_redraw:
            plt.draw()
        self.need_redraw = False