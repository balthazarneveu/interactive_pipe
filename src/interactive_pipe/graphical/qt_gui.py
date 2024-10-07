import time
from pathlib import Path
import sys
import numpy as np
from typing import List
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.headless.keyboard import KeyboardControl
from interactive_pipe.graphical.qt_control import ControlFactory
from interactive_pipe.graphical.window import InteractivePipeWindow
from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.headless.control import Control
import logging
PYQTVERSION = None
MPL_SUPPORT = False

if not PYQTVERSION:
    try:
        from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QFormLayout, QGridLayout, QHBoxLayout, QVBoxLayout, QHBoxLayout, QMessageBox
        from PyQt6.QtCore import QUrl, Qt
        from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
        from PyQt6.QtGui import QPixmap, QImage, QIcon
        PYQTVERSION = 6
    except ImportError:
        logging.warning("Cannot import PyQt 6")
        try:
            from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QFormLayout, QGridLayout, QHBoxLayout, QVBoxLayout, QHBoxLayout, QMessageBox
            from PyQt5.QtCore import QUrl, Qt
            from PyQt5.QtGui import QPixmap, QImage, QIcon
            from PyQt5.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaContent
            PYQTVERSION = 5
            logging.warning("Using PyQt 5")
        except:
            raise ModuleNotFoundError("No PyQt")

if not PYQTVERSION:
    try:
        from PySide6.QtWidgets import QApplication, QWidget, QLabel, QFormLayout, QGridLayout, QHBoxLayout, QVBoxLayout, QHBoxLayout, QMessageBox
        from PySide6.QtCore import QUrl, Qt
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        from PySide6.QtGui import QPixmap, QImage, QIcon
        PYQTVERSION = 6
    except ImportError:
        logging.warning("Cannot import PySide 6")

if not PYQTVERSION:
    logging.warning("Cannot import PyQt or PySide - disable backend")
try:
    from matplotlib.backends.backend_qtagg import (
        FigureCanvas, NavigationToolbar2QT as NavigationToolbar)
    from matplotlib.figure import Figure
    from interactive_pipe.data_objects.curves import Curve, SingleCurve
    MPL_SUPPORT = True
except ImportError:
    logging.warning("No support for Matplotlib widgets for Qt")


class InteractivePipeQT(InteractivePipeGUI):
    def init_app(self, **kwargs):
        if not QApplication.instance():
            self.app = QApplication(sys.argv)
        else:
            self.app = QApplication.instance()

        if self.audio:
            self.audio_player()
        self.window = MainWindow(controls=self.controls, name=self.name,
                                 pipeline=self.pipeline, size=self.size, main_gui=self, **kwargs)
        self.pipeline.global_params["__pipeline"] = self.pipeline
        self.set_default_key_bindings()

    def run(self) -> list:
        assert self.pipeline._PipelineCore__initialized_inputs, "Did you forget to initialize the pipeline inputs?"
        self.window.refresh()
        ret = self.app.exec()
        self.custom_end()
        return self.pipeline.results

    def set_default_key_bindings(self):
        self.key_bindings = {**{
            "f1": self.help,
            "f11": self.toggle_full_screen,
            "r": self.reset_parameters,
            "w": self.save_images,
            "o": self.load_parameters,
            "e": self.save_parameters,
            "i": self.print_parameters,
            "q": self.close,
            "g": self.display_graph
        }, **self.key_bindings}

    def close(self):
        """close GUI"""
        self.app.quit()

    def reset_parameters(self):
        """reset sliders to default parameters"""
        super().reset_parameters()
        for widget_idx, ctrl in self.window.ctrl.items():
            ctrl.value = ctrl.value_default
        self.window.reset_sliders()

    def load_parameters(self):
        """import parameters dictionary from a yaml/json file on disk"""
        super().load_parameters()
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

    def print_message(self, message_list: List[str]):
        print("\n".join(message_list))
        QMessageBox.about(self.window, self.name, "\n".join(message_list))

    def toggle_full_screen(self):
        """toggle full screen"""
        if not hasattr(self, "full_screen_toggle"):
            self.full_screen_toggle = self.window.full_screen_flag
        self.full_screen_toggle = not self.full_screen_toggle
        if self.full_screen_toggle:
            # Go to fullscreen
            self.window.full_screen()
        else:
            window_size = self.window.size
            if window_size is not None and isinstance(window_size, str) and "full" in window_size.lower():
                # Special case where the window naturally goes to fullscreen since user defined it...
                # Force to go back to normal
                self.window.showNormal()
            else:  # Go back to normal size
                self.window.update_window()

    # ---------------------------- AUDIO FEATURE ----------------------------------------

    def audio_player(self):
        self.player = QMediaPlayer()
        if PYQTVERSION == 6:
            self.audio_output = QAudioOutput()
            self.player.setAudioOutput(self.audio_output)
            self.audio_output.setVolume(50)
            self.player.errorChanged.connect(self.handle_audio_error)
        else:
            self.player.setVolume(50)
            currentVolume = self.player.volume()
            self.player.error.connect(self.handle_audio_error)
        self.pipeline.global_params["__player"] = self.player
        self.pipeline.global_params["__set_audio"] = self.__set_audio
        self.pipeline.global_params["__play"] = self.__play
        self.pipeline.global_params["__pause"] = self.__pause
        self.pipeline.global_params["__stop"] = self.__stop

    def handle_audio_error(self):
        print("Error: " + self.player.errorString())

    def __set_audio(self, file_path):
        self.__stop()
        time.sleep(0.01)
        if isinstance(file_path, str):
            file_path = Path(file_path)
        assert file_path.exists()
        file_path = Path.cwd() / file_path
        media_url = QUrl.fromLocalFile(str(file_path))
        if PYQTVERSION == 6:
            self.player.setSource(media_url)
        else:
            content = QMediaContent(media_url)
            self.player.setMedia(content)
            self.player.play()
        time.sleep(0.01)
        self.player.setPosition(0)

    def __play(self):
        self.player.play()

    def __pause(self):
        self.player.pause()

    def __stop(self):
        self.player.stop()


class MainWindow(QWidget, InteractivePipeWindow):
    key_mapping_dict = {
        Qt.Key.Key_Up: KeyboardControl.KEY_UP,
        Qt.Key.Key_Down: KeyboardControl.KEY_DOWN,
        Qt.Key.Key_Left: KeyboardControl.KEY_LEFT,
        Qt.Key.Key_Right: KeyboardControl.KEY_RIGHT,
        Qt.Key.Key_PageUp: KeyboardControl.KEY_PAGEUP,
        Qt.Key.Key_PageDown: KeyboardControl.KEY_PAGEDOWN,
        Qt.Key.Key_F1: "f1",
        Qt.Key.Key_F2: "f2",
        Qt.Key.Key_F3: "f3",
        Qt.Key.Key_F4: "f4",
        Qt.Key.Key_F5: "f5",
        Qt.Key.Key_F6: "f6",
        Qt.Key.Key_F7: "f7",
        Qt.Key.Key_F8: "f8",
        Qt.Key.Key_F9: "f9",
        Qt.Key.Key_F10: "f10",
        Qt.Key.Key_F11: "f11",
        Qt.Key.Key_F12: "f12",
        Qt.Key.Key_Space: KeyboardControl.KEY_SPACEBAR,
    }

    def __init__(self, *args, controls=[], name="", pipeline: HeadlessPipeline = None, size=None, center=True, style=None, main_gui=None, **kwargs):
        QWidget.__init__(self, *args, **kwargs)
        InteractivePipeWindow.__init__(
            self, name=name, pipeline=pipeline, size=size)
        self.main_gui = main_gui
        self.pipeline.global_params["__window"] = self
        self.setWindowTitle(self.name)

        self.layout_obj = QFormLayout()
        self.setLayout(self.layout_obj)

        if center:
            self.image_grid_layout = QGridLayout()

            # Create QHBoxLayout for horizontal centering
            horizontal_centering_layout = QHBoxLayout()
            horizontal_centering_layout.addStretch()  # Add stretch to left side
            horizontal_centering_layout.addLayout(self.image_grid_layout)
            horizontal_centering_layout.addStretch()  # Add stretch to right side

            # Create QVBoxLayout for vertical centering
            vertical_centering_layout = QVBoxLayout()
            vertical_centering_layout.addStretch()  # Add stretch to top
            vertical_centering_layout.addLayout(horizontal_centering_layout)
            vertical_centering_layout.addStretch()  # Add stretch to bottom

            self.layout_obj.addRow(vertical_centering_layout)
        else:
            self.image_grid_layout = QGridLayout(self)
            self.layout_obj.addRow(self.image_grid_layout)

        self.init_sliders(controls)
        # if self.pipeline._PipelineCore__initialized_inputs:
        #     # cannot refresh the pipeline if no input has been provided! ... not ok for inputless pipeline though!
        #     self.refresh()
        # # You will refresh the window  at the app level, only when running. no need to run the pipeline engine to initalize the GUI
        self.size = size
        self.full_screen_flag = False

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.show()

    @property
    def size(self):
        return self._size

    @size.setter
    def size(self, _size):
        if isinstance(_size, str):
            assert "full" in _size.lower() or "max" in _size.lower(
            ), f"size={_size} can only be among (full, fullscreen, maximized, max, maximum)"
        self._size = _size
        self.update_window()

    def update_window(self):
        self.full_screen_flag = False
        if self.size is None:
            self.showNormal()
            return
        if isinstance(self.size, str):
            if "max" in self.size.lower():
                self.maximize_screen()
            if "full" in self.size.lower():
                self.full_screen()
        else:
            self.showNormal()
            if isinstance(self.size, int):
                self.setMinimumWidth(self.size)
            elif isinstance(self.size, tuple) or isinstance(self.size, list):
                self.setMinimumWidth(self.size[0])
                self.setMinimumHeight(self.size[1])

    def full_screen(self):
        self.showFullScreen()
        self.full_screen_flag = True

    def maximize_screen(self):
        self.showMaximized()
        self.full_screen_flag = False

    def keyPressEvent(self, event):
        mapped_str = None

        current_key = event.key()
        for qt_key, str_mapping in self.key_mapping_dict.items():
            if current_key == qt_key:
                mapped_str = str_mapping
                logging.debug(f"matched Qt key{mapped_str}")
        if mapped_str is None:
            mapped_str = event.text()
        self.main_gui.on_press(mapped_str, refresh_func=self.refresh)

    def init_sliders(self, controls: List[Control]):
        self.ctrl = {}
        self.result_label = {}
        self.name_label = {}
        self.widget_list = {}
        control_factory = ControlFactory()
        vertical_spacing = 1  # Decrease this value to reduce vertical space between sliders
        self.layout_obj.setSpacing(vertical_spacing)
        for ctrl in controls:
            slider_name = ctrl.name
            self.ctrl[slider_name] = ctrl
            if isinstance(ctrl, KeyboardControl):
                self.main_gui.bind_keyboard_slider(
                    ctrl, self.key_update_parameter)
            elif isinstance(ctrl, Control):
                slider_instance = control_factory.create_control(
                    ctrl, self.update_parameter)
                slider_or_layout = slider_instance.create()
                self.widget_list[slider_name] = slider_instance

                slider_layout = QHBoxLayout()

                if isinstance(slider_or_layout, QWidget):
                    label_fixed_width = 200
                    label = QLabel('', self)
                    label.setMinimumWidth(label_fixed_width)
                    self.name_label[slider_name] = label
                    slider_layout.addWidget(self.name_label[slider_name])
                if isinstance(slider_or_layout, QWidget):
                    # If it's a QWidget, add it directly to the layout
                    slider_layout.addWidget(slider_or_layout)
                elif isinstance(slider_or_layout, QHBoxLayout):
                    slider_or_layout.setContentsMargins(0, 0, 0, 0)
                    # If it's a QHBoxLayout, embed it in a QWidget first
                    container_widget = QWidget()
                    container_widget.setLayout(slider_or_layout)
                    slider_layout.addWidget(container_widget)
                else:
                    print(
                        f"Unhandled type for slider: {type(slider_or_layout)}")
                    continue
                if isinstance(slider_or_layout, QWidget):
                    result_fixed_width = 100
                    label = QLabel('', self)
                    label.setMinimumWidth(result_fixed_width)
                    self.result_label[slider_name] = label
                    slider_layout.addWidget(self.result_label[slider_name])

                # Create a container widget for the entire row
                row_container_widget = QWidget()
                row_container_widget.setLayout(slider_layout)
                # Set a fixed height for the row container

                # fixed_height = None
                # if ctrl._type is float or ctrl._type is int:
                #     fixed_height = 32 # Adjust this value as needed
                # elif ctrl._type is bool:
                #     pass
                # if fixed_height is not None:
                #     row_container_widget.setFixedHeight(fixed_height)
                row_container_widget.setContentsMargins(
                    0, 0, 0, 0)  # Adjust these values as needed

                self.layout_obj.addRow(row_container_widget)

                self.update_label(slider_name)

    def update_label(self, idx):
        # pass
        val = self.ctrl[idx].value
        val_to_print = val
        if isinstance(val, float):
            val_to_print = f"{val:.3e}"
        if idx in self.result_label.keys():
            self.result_label[idx].setText(f'{val_to_print}')
        if idx in self.name_label.keys():
            self.name_label[idx].setText(f'{self.ctrl[idx].name}')

    def update_parameter(self, idx, value):
        """Required implementation for graphical controllers update"""
        if self.ctrl[idx]._type == str:
            self.ctrl[idx].update(self.ctrl[idx].value_range[value])
        elif self.ctrl[idx]._type == bool:
            self.ctrl[idx].update(bool(value))
        elif self.ctrl[idx]._type == float:
            self.ctrl[idx].update(self.ctrl[idx].convert_int_to_value(value))
        elif self.ctrl[idx]._type == int:
            self.ctrl[idx].update(value)
        else:
            raise NotImplementedError("{self.ctrl[idx]._type} not supported")
        self.update_label(idx)
        self.refresh()

    def key_update_parameter(self, idx, down):
        """Required implementation for keyboard sliders update"""
        if down:
            self.ctrl[idx].on_key_down()
        else:
            self.ctrl[idx].on_key_up()
        # self.update_label(idx)
        self.refresh()

    def add_image_placeholder(self, row, col):
        ax_placeholder = None
        image_label = QLabel(self)
        text_label = QLabel(text=f"{row} {col}")
        self.image_canvas[row][col] = {
            "image": image_label, "title": text_label, "ax_placeholder": ax_placeholder}
        self.image_grid_layout.addWidget(
            text_label, 2*row, col, alignment=Qt.AlignmentFlag.AlignCenter)
        self.image_grid_layout.addWidget(
            image_label, 2*row+1, col, alignment=Qt.AlignmentFlag.AlignCenter)

    def delete_image_placeholder(self, img_widget_dict):
        for obj_key, img_widget in img_widget_dict.items():
            if obj_key == "plot_object":
                img_widget = None
            elif obj_key == "ax_placeholder" and img_widget is not None:
                img_widget.remove()
            elif img_widget is not None:
                img_widget.setParent(None)

    def update_image(self, image_array_original, row, col):
        if isinstance(image_array_original, np.ndarray) and len(image_array_original.shape) == 1:
            logging.warning("Audio playback not supported with 1D signal" +
                            "\nuse live audio instead while using Qt!" +
                            "\nuse instead: context['__set_audio'](audio_track)" +
                            "\nSee example here: https://github.com/balthazarneveu/interactive_pipe/blob/master/demo/jukebox.py")
            logging.warning("We'll try to display the audio signal as an image instead")
            image_array_original = Curve([
                SingleCurve(
                    # x=np.linspace(0, image_array_original.shape[0]/44100, image_array_original.shape[0]),
                    y=image_array_original,
                    # style="k"
                )
            ],
                # xlabel="Time[s]",
                ylabel="Amplitude",
            )
        elif isinstance(image_array_original, np.ndarray) and len(image_array_original.shape) > 1:
            if len(image_array_original.shape) == 2:
                # Consider black & white
                image_array = image_array_original.copy()
                c = 3
                image_array = np.expand_dims(image_array, axis=-1)
                image_array = np.repeat(image_array, c, axis=-1)
            elif len(image_array_original.shape) == 3:
                assert isinstance(image_array_original, np.ndarray)
                assert (image_array_original.shape[-1]) == 3
                image_array = image_array_original
            else:
                raise NotImplementedError(
                    f"{image_array_original.shape}4 dimensions image or more like burst are not supported")
            h, w, c = image_array.shape
            bytes_per_line = c * w
            image = QImage(image_array.data, w, h, bytes_per_line,
                           QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(image)
            image_label = self.image_canvas[row][col]["image"]
            image_label.setPixmap(pixmap)
        if not isinstance(image_array_original, np.ndarray):
            image_array = image_array_original
            if MPL_SUPPORT and isinstance(image_array, Curve):
                image_label = FigureCanvas(Figure(figsize=(10, 10)))
                if self.image_canvas[row][col]["ax_placeholder"] is None:
                    ax_placeholder = image_label.figure.subplots()
                    self.image_canvas[row][col]["image"] = image_label
                    self.image_grid_layout.addWidget(
                        image_label, 2*row+1, col, alignment=Qt.AlignmentFlag.AlignCenter)
                    self.image_canvas[row][col]["ax_placeholder"] = ax_placeholder
                ax = self.image_canvas[row][col]["ax_placeholder"]
                plt_obj = self.image_canvas[row][col].get("plot_object", None)
                if plt_obj is None:
                    self.image_canvas[row][col]["plot_object"] = image_array.create_plot(
                        ax=ax)
                else:
                    image_array.update_plot(plt_obj, ax=ax)
                    ax.figure.canvas.draw()

        text_label = self.image_canvas[row][col]["title"]
        text_label.setText(self.get_current_style(row, col).get("title", ""))

    @staticmethod
    def convert_image(out_im):
        if isinstance(out_im, np.ndarray) and len(out_im.shape) > 1:
            return (out_im.clip(0., 1.) * 255).astype(np.uint8)
        else:
            return out_im

    def refresh(self):
        if self.pipeline is not None:
            out = self.pipeline.run()
            self.refresh_display(out)

    def reset_sliders(self):
        for widget_idx, ctrl in self.ctrl.items():
            if widget_idx in self.widget_list.keys():
                self.widget_list[widget_idx].reset()
            self.update_label(widget_idx)
        self.refresh()
