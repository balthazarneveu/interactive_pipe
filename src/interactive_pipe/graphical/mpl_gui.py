from interactive_pipe.graphical.gui import InteractivePipeGUI
import matplotlib.pyplot as plt
from interactive_pipe.headless.keyboard import KeyboardControl
from typing import List, Optional, Union, Tuple
import logging
from interactive_pipe.graphical.mpl_control import ControlFactory
from interactive_pipe.graphical.mpl_window import MatplotlibWindow


class InteractivePipeMatplotlib(InteractivePipeGUI):
    """Interactive image pipe with matplotlib backend
    """

    def init_app(self, **kwargs):
        self.window = MainWindow(controls=self.controls, name=self.name,
                                 pipeline=self.pipeline, main_gui=self, size=self.size, **kwargs)
        self.set_default_key_bindings()

    def set_default_key_bindings(self):
        self.key_bindings = {
            **{
                "f1": self.help,
                "r": self.reset_parameters,
                "w": self.save_images,
                "o": self.load_parameters,
                "e": self.save_parameters,
                "i": self.print_parameters,
                "q": self.close,
                "g": self.display_graph
            },
            **self.key_bindings
        }

    def run(self) -> list:
        assert self.pipeline._PipelineCore__initialized_inputs, "Did you forget to initialize the pipeline inputs?"
        self.window.refresh()
        if isinstance(self.size, str) and "full" in self.size.lower():
            try:
                mng = plt.get_current_fig_manager()
                mng.full_screen_toggle()
            except Exception as exc:
                print(exc)
                logging.warning("Cannot maximize screen")
        self.window.fig.canvas.mpl_disconnect(
            self.window.fig.canvas.manager.key_press_handler_id)
        self.window.fig.canvas.mpl_connect('key_press_event', self.on_press)
        plt.show()
        return self.pipeline.results

    def load_parameters(self):
        """import parameters dictionary from a yaml/json file on disk"""
        super().load_parameters()
        self.window.need_redraw = True
        # @TODO: issue #18 - https://github.com/balthazarneveu/interactive_pipe/issues/18
        # Requires mapping the parameters back into each Control objects
        print("------------")
        for widget_idx, widget in self.window.ctrl.items():
            matched = False
            for filtname, params in self.pipeline.parameters.items():
                for param_name in params.keys():
                    if param_name == widget.parameter_name_to_connect:
                        print(
                            f"MATCH & update {filtname} {widget_idx} with {self.pipeline.parameters[filtname][param_name]}")
                        self.window.ctrl[widget_idx].update(
                            self.pipeline.parameters[filtname][param_name])
                        matched = True
            assert matched, f"could not match widget {widget_idx} with parameter to connect {widget.parameter_name_to_connect}"
        print("------------")
        self.window.reset_sliders()

    def reset_parameters(self):
        """reset sliders to default parameters"""
        super().reset_parameters()
        for widget_idx, widget in self.window.ctrl.items():
            widget.value = widget.value_default
        self.window.reset_sliders()

    def close(self):
        """close GUI"""
        super().close()
        plt.close(self.window.fig)

    def on_press(self, event):
        super().on_press(event.key, refresh_func=self.refresh)

    def refresh(self):
        # main GUI needs to be able to force the underlying window to refres
        # in case of a special key press event!
        self.window.need_redraw = True
        self.window.refresh()


class MainWindow(MatplotlibWindow):
    def __init__(self,  controls=[], name="", pipeline=None, size: Optional[Union[str, int, Tuple[int, int]]] = None, style: str = None, rc_params=None, main_gui=None, **kwargs):
        if size is not None and isinstance(size, int):
            size = (size, size)
        if isinstance(size, str):
            assert "full" in size.lower(
            ), f"size={size} can be only fullscreen or full"
        super().__init__(controls=controls, name=name, pipeline=pipeline,
                         style=style, size=size, rc_params=rc_params, **kwargs)
        self.main_gui = main_gui
        self.fig, self.ax = plt.subplots(figsize=self.size if isinstance(
            self.size, tuple) else None, num=self.name)
        plt.axis('off')
        self.init_sliders()

    def reset_sliders(self):
        self.__wipe_sliders()
        self.init_sliders()
        self.refresh()

    def __wipe_sliders(self):
        for ax in self.axes_controls:
            ax.remove()

    def init_sliders(self, dry_run_only=False):
        plt.subplots_adjust(left=0, top=1, bottom=0, right=1)
        # Compute the space needed for slider (dry_run) -> go down
        self.spacer = 0.005
        self.footer_space = 0.01
        self.next_slider_position = self.next_button_position = 0.
        self.__init_sliders(dry_run=True)
        # Then go back up.
        self.next_slider_position *= -1
        self.next_button_position *= -1
        # Then go through the slider and create dedicated figures & widgets
        self.top_of_sliders = max(
            self.next_slider_position,  self.next_button_position)
        self.__init_sliders()
        plt.subplots_adjust(
            left=0.04, top=0.97, bottom=self.top_of_sliders + 2*self.spacer, right=1-0.04)

    def __init_sliders(self, dry_run=False):
        if not dry_run:
            self.ctrl = {}
            self.result_label = {}
            control_factory = ControlFactory()
            self.sliders_list = {}
            self.axes_controls = []

        for ctrl in self.controls:
            slider_name = ctrl.name
            if not dry_run:
                self.ctrl[slider_name] = ctrl
            if isinstance(ctrl, KeyboardControl):
                self.main_gui.bind_keyboard_slider(
                    ctrl, self.key_update_parameter)
                continue
            if ctrl._type == bool or ctrl._type == str:
                x_start = 0.01
                width = 0.08
                number_of_items = (1 if ctrl._type ==
                                   bool else len(ctrl.value_range))
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
                ax_control = self.fig.add_axes(
                    [x_start, y_start, width, height])
                if ctrl._type == bool:
                    ax_control.xaxis.set_visible(True)
                self.axes_controls.append(ax_control)
                slider_instance = control_factory.create_control(
                    ctrl, self.update_parameter, ax_control=ax_control)
                slider = slider_instance.create()
                # needed to keep the object alive
                self.sliders_list[slider_name] = slider
        self.next_slider_position -= self.footer_space
        self.next_button_position -= self.footer_space

    def update_parameter(self, idx, value):
        """Required implementation for graphical controllers update"""
        self.ctrl[idx].update(value)
        if self.ctrl[idx]._type == bool or self.ctrl[idx]._type == str:
            self.need_redraw = True
        self.refresh()

    def key_update_parameter(self, idx, down):
        """Required implementation for keyboard sliders update"""
        if down:
            self.ctrl[idx].on_key_down()
        else:
            self.ctrl[idx].on_key_up()
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
