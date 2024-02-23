from interactive_pipe.graphical.gui import InteractivePipeGUI
import matplotlib.pyplot as plt
from interactive_pipe.headless.control import Control
from typing import List
from interactive_pipe.graphical.nb_control import ControlFactory

from IPython.display import display
from ipywidgets import interact
from interactive_pipe.graphical.mpl_window import MatplotlibWindow
from typing import Optional, Tuple, Union


class InteractivePipeJupyter(InteractivePipeGUI):
    def init_app(self, **kwargs):
        self.window = MainWindow(controls=self.controls, name=self.name,
                                 pipeline=self.pipeline, size=self.size, **kwargs)

    def run(self) -> None:
        assert self.pipeline._PipelineCore__initialized_inputs, "Did you forget to initialize the pipeline inputs?"
        interact(self.window._interact_fn, **self.window.sliders_dict)
        return None  # do not return arrays in a jupyter notebook

# You will need %matplotlib inline


class MainWindow(MatplotlibWindow):
    def __init__(self,  controls=[], name="", pipeline=None, size: Optional[Union[int, Tuple[int, int]]] = None, style: str = None, rc_params=None):
        if size is not None and isinstance(size, int):
            size = (size, size)
        assert size is None or isinstance(size, tuple) or isinstance(
            size, list), "size should be a tuple or None"

        super().__init__(controls=controls, name=name, pipeline=pipeline,
                         style=style, rc_params=rc_params, size=size)
        self.init_sliders(self.controls)

    def create_figure(self):
        if not hasattr(self, "fig"):
            self.fig, self.ax = plt.subplots(figsize=self.size)
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
            # needed to keep the object alive
            self.sliders_dict[slider_name] = slider_widget
            self.ctrl[slider_name] = ctrl

    def _interact_fn(self, **kwargs):
        for idx, param in kwargs.items():
            self.ctrl[idx].update(param)
        self.refresh()
        display(self.fig)

    def refresh(self):
        if self.pipeline is not None:
            out = self.pipeline.run()
            self.create_figure()
            self.refresh_display(out)
