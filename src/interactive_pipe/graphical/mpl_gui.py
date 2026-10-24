import logging
from typing import Optional, Tuple, Union

import matplotlib.pyplot as plt

from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.graphical.mpl_control import ControlFactory
from interactive_pipe.graphical.mpl_window import MatplotlibWindow
from interactive_pipe.headless.keyboard import KeyboardControl


class InteractivePipeMatplotlib(InteractivePipeGUI):
    """Interactive image pipe with matplotlib backend"""

    def init_app(self, **kwargs):
        self.window = MainWindow(
            controls=self.controls,
            name=self.name,
            pipeline=self.pipeline,
            main_gui=self,
            size=self.size,
            **kwargs,
        )
        self.set_default_key_bindings()

    def run(self) -> list:
        # Access private attribute for checking initialization state
        if not self.pipeline._PipelineCore__initialized_inputs:  # type: ignore[attr-defined]
            raise RuntimeError("Did you forget to initialize the pipeline inputs?")
        self.window.refresh()
        if isinstance(self.size, str) and "full" in self.size.lower():
            try:
                mng = plt.get_current_fig_manager()
                if mng is not None and hasattr(mng, "full_screen_toggle"):
                    mng.full_screen_toggle()
            except Exception as exc:
                # Broad on purpose: full-screen toggling is cosmetic and
                # backend-specific; never crash over it.
                logging.warning(f"Cannot maximize screen: {exc}")
        if self.window.fig is None:
            raise RuntimeError("Window figure not initialized")
        if hasattr(self.window.fig.canvas, "manager") and self.window.fig.canvas.manager is not None:
            handler_id = getattr(self.window.fig.canvas.manager, "key_press_handler_id", None)
            if handler_id is not None:
                self.window.fig.canvas.mpl_disconnect(handler_id)
        self.window.fig.canvas.mpl_connect("key_press_event", self.on_press)
        plt.show()
        results = self.pipeline.results
        if results is None:
            return []
        if isinstance(results, tuple):
            return list(results)
        return results if isinstance(results, list) else []

    def on_parameters_loaded(self):
        """sync the widgets with the imported parameters"""
        # HeadlessPipeline.parameters (set by import_tuning) writes the loaded
        # values back into the connected controls; the widgets just need rebuilding.
        self.window.need_redraw = True
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
    def __init__(
        self,
        controls=None,
        name="",
        pipeline=None,
        size: Optional[Union[str, int, Tuple[int, int]]] = None,
        style: Optional[str] = None,
        rc_params=None,
        main_gui=None,
        **kwargs,
    ):
        if controls is None:
            controls = []
        if size is not None and isinstance(size, int):
            size = (size, size)
        if isinstance(size, str):
            if "full" not in size.lower():
                raise ValueError(f"size={size} can be only fullscreen or full")
        super().__init__(
            controls=controls,
            name=name,
            pipeline=pipeline,
            style=style,
            size=size,
            rc_params=rc_params,
            **kwargs,
        )
        self.main_gui = main_gui
        figsize = self.window_size if isinstance(self.window_size, tuple) else None
        self.fig, self.ax = plt.subplots(figsize=figsize, num=self.name)
        plt.axis("off")
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
        self.next_slider_position = self.next_button_position = 0.0
        self.__init_sliders(dry_run=True)
        # Then go back up.
        self.next_slider_position *= -1
        self.next_button_position *= -1
        # Then go through the slider and create dedicated figures & widgets
        self.top_of_sliders = max(self.next_slider_position, self.next_button_position)
        self.__init_sliders()
        plt.subplots_adjust(
            left=0.04,
            top=0.97,
            bottom=self.top_of_sliders + 2 * self.spacer,
            right=1 - 0.04,
        )

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
                if not dry_run and self.main_gui is not None:
                    self.main_gui.bind_keyboard_slider(ctrl, self.key_update_parameter)
                continue
            # Skip single-value controls (don't show anything)
            if ctrl._type is str and ctrl.value_range is not None and len(ctrl.value_range) == 1:
                continue
            if ctrl._type is bool or (ctrl._type is str and ctrl.value_range is not None):
                x_start = 0.01
                width = 0.08
                number_of_items = 1 if (ctrl._type is bool or ctrl.value_range is None) else len(ctrl.value_range)
                height = 0.02 * number_of_items
                y_start = self.next_slider_position - height
                self.next_slider_position -= self.spacer + height
            elif ctrl._type in (float, int, str):
                x_start = 0.25
                width = 0.65
                # sliders are thin, text entries (str prompt / rangeless numbers) taller
                height = 0.02 if ctrl.value_range is not None else 0.05
                y_start = self.next_button_position - height
                self.next_button_position -= self.spacer + height
            else:
                continue
            if not dry_run:
                if self.fig is None:
                    raise RuntimeError("Figure not initialized")
                ax_control = self.fig.add_axes((x_start, y_start, width, height))
                if ctrl._type is bool:
                    ax_control.xaxis.set_visible(True)
                self.axes_controls.append(ax_control)
                slider_instance = control_factory.create_control(ctrl, self.update_parameter, ax_control=ax_control)
                if slider_instance is not None:
                    slider = slider_instance.create()
                    # needed to keep the object alive
                    self.sliders_list[slider_name] = slider
        self.next_slider_position -= self.footer_space
        self.next_button_position -= self.footer_space

    def update_parameter(self, idx, value):
        """Required implementation for graphical controllers update"""
        self.ctrl[idx].update(value)
        if self.ctrl[idx]._type is bool or self.ctrl[idx]._type is str:
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
