PYQTVERSION = None
import logging

try:
    from PySide6.QtWidgets import QApplication, QWidget, QLabel, QFormLayout, QGridLayout, QHBoxLayout, QVBoxLayout, QHBoxLayout, QMessageBox
    from PySide6.QtCore import QUrl, Qt
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtGui import QPixmap, QImage, QIcon
    PYQTVERSION = 6
except:
    logging.warning("Cannot import PySide 6")
    
if not PYQTVERSION:
    try:
            from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QFormLayout, QGridLayout, QHBoxLayout, QVBoxLayout, QHBoxLayout, QMessageBox
            from PyQt6.QtCore import QUrl, Qt
            from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
            from PyQt6.QtGui import QPixmap, QImage, QIcon
            PYQTVERSION = 6
    except:
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


from interactive_pipe.core.control import Control
from interactive_pipe.graphical.gui import InteractivePipeGUI, InteractivePipeWindow
from interactive_pipe.graphical.qt_control import ControlFactory
from interactive_pipe.graphical.keyboard import KeyboardSlider
from interactive_pipe.headless.pipeline import HeadlessPipeline
from typing import List
import numpy as np

import sys
import logging
from pathlib import Path
import time


class InteractivePipeQT(InteractivePipeGUI):    
    def init_app(self, **kwargs):
        self.app = QApplication(sys.argv)
        if self.audio:
            self.audio_player()
        self.window = MainWindow(controls=self.controls, name=self.name, pipeline=self.pipeline, size=self.size, main_gui=self, **kwargs)
        self.pipeline.global_params["__pipeline"] = self.pipeline
        self.set_default_key_bindings()
        
    def run(self):
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
                        print(f"MATCH & update {filtname} {widget_idx} with {self.pipeline.parameters[filtname][param_name]}")
                        self.window.ctrl[widget_idx].update(self.pipeline.parameters[filtname][param_name])
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
            else: # Go back to normal size
                self.window.update_window()
        

    
    ### ---------------------------- AUDIO FEATURE ----------------------------------------
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
        Qt.Key_Up: "up",
        Qt.Key_Down: "down",
        Qt.Key_Left: "left",
        Qt.Key_Right: "right",
        Qt.Key_PageUp: "pageup",
        Qt.Key_PageDown: "pagedown",
        Qt.Key_F1 : "f1",
        Qt.Key_F2 : "f2",
        Qt.Key_F3 : "f3",
        Qt.Key_F4 : "f4",
        Qt.Key_F5 : "f5",
        Qt.Key_F6 : "f6",
        Qt.Key_F7 : "f7",
        Qt.Key_F8 : "f8",
        Qt.Key_F9 : "f9",
        Qt.Key_F10 : "f10",
        Qt.Key_F11 : "f11",
        Qt.Key_F12 : "f12",
        Qt.Key_Space : " ",
    }
    def __init__(self, *args, controls=[], name="", pipeline: HeadlessPipeline=None, size=None, center=True, style=None, main_gui=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.pipeline = pipeline
        self.main_gui = main_gui
        self.pipeline.global_params["__window"] = self
        self.setWindowTitle(name)

        self.layout_obj = QFormLayout()
        self.setLayout(self.layout_obj)
        if pipeline.outputs:
            if not isinstance(pipeline.outputs[0], list):
                pipeline.outputs = [pipeline.outputs]
        

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
        self.full_screen_flag = False
        self.size = size
        
        self.setFocusPolicy(Qt.StrongFocus)
        self.show()

    @property
    def size(self):
        return self._size

    @size.setter
    def size(self, _size):
        if isinstance(_size, str):
            assert "full" in _size.lower() or "max" in _size.lower(), f"size={_size} can only be among (full, fullscreen, maximized, max, maximum)"
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
            if current_key ==qt_key:
                mapped_str = str_mapping
                logging.debug(f"matched Qt key{mapped_str}")  
        if mapped_str is None:
            mapped_str = event.text()   
        self.main_gui.on_press(mapped_str, refresh_func=self.refresh)

    def init_sliders(self, controls: List[Control]):
        self.ctrl = {}
        self.result_label = {}
        self.widget_list = {}
        control_factory = ControlFactory()
        for ctrl in controls:
            slider_name = ctrl.name
            self.ctrl[slider_name] = ctrl
            if isinstance(ctrl, KeyboardSlider):
                self.main_gui.bind_keyboard_slider(ctrl, self.key_update_parameter)
            elif isinstance(ctrl, Control):
                slider_instance = control_factory.create_control(ctrl, self.update_parameter)
                slider = slider_instance.create()
                self.widget_list[slider_name] = slider_instance
                self.layout_obj.addRow(slider)
            
            self.result_label[slider_name] = QLabel('', self)
            self.layout_obj.addRow(self.result_label[slider_name])   
            self.update_label(slider_name)

    def update_label(self, idx):
        self.result_label[idx].setText(f'{self.ctrl[idx].name} = {self.ctrl[idx].value}')

    def update_parameter(self, idx, value):
        """Required implementation for graphical controllers update"""
        if self.ctrl[idx]._type == str:
            self.ctrl[idx].update(self.ctrl[idx].value_range[value])
        elif self.ctrl[idx]._type == bool:
            self.ctrl[idx].update(bool(value))
        elif self.ctrl[idx]._type == float:
                self.ctrl[idx].update(value/100.)
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
        self.update_label(idx)
        self.refresh()

    def add_image_placeholder(self, row, col):
        self.image_canvas[row][col] = QLabel(self)
        self.image_grid_layout.addWidget(self.image_canvas[row][col], row, col)

    def delete_image_placeholder(self, img_widget):
        img_widget.setParent(None)

    def update_image(self, image_array, row, col):
        h, w, c = image_array.shape
        bytes_per_line = c * w
        image = QImage(image_array.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(image)                
        label = self.image_canvas[row][col]
        label.setPixmap(pixmap)

    @staticmethod
    def convert_image(out_im):
        return (out_im.clip(0., 1.)  * 255).astype(np.uint8)

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
