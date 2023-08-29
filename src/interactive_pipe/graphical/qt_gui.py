PYQTVERSION = None
import logging

try:
    from PySide6.QtWidgets import QApplication, QWidget, QLabel, QFormLayout, QGridLayout, QHBoxLayout, QVBoxLayout, QHBoxLayout
    from PySide6.QtCore import QUrl
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtGui import QPixmap, QImage, QIcon
    PYQTVERSION = 6
except:
    logging.warning("Cannot import PySide 6")
    
if not PYQTVERSION:
    try:
            from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QFormLayout, QGridLayout, QHBoxLayout, QVBoxLayout, QHBoxLayout
            from PyQt6.QtCore import QUrl
            from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
            from PyQt6.QtGui import QPixmap, QImage, QIcon
            PYQTVERSION = 6
    except:
        logging.warning("Cannot import PyQt 6")
        try:
            from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QFormLayout, QGridLayout, QHBoxLayout, QVBoxLayout, QHBoxLayout
            from PyQt5.QtCore import QUrl
            from PyQt5.QtGui import QPixmap, QImage, QIcon
            from PyQt5.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaContent
            PYQTVERSION = 5
            logging.warning("Using PyQt 5")
        except:
            raise ModuleNotFoundError("No PyQt")


from interactive_pipe.core.control import Control
from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.graphical.qt_control import ControlFactory

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
        self.window = MainWindow(controls=self.controls, name=self.name, pipeline=self.pipeline, **kwargs)

    def run(self):
        ret = self.app.exec()
        self.custom_end()
        sys.exit(ret)

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



class MainWindow(QWidget):
    def __init__(self, *args, controls=[], name="", pipeline=None, fullscreen=False, width=None, center=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.pipeline = pipeline
        self.pipeline.global_params["__window"] = self
        
        self.image_canvas = None
        self.setWindowTitle(name)
        if width is not None:
            self.setMinimumWidth(width)
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
        self.refresh()
        if width is None:
            self.showMaximized()
        if fullscreen:
            self.showFullScreen()
        self.show()

    def init_sliders(self, controls: List[Control]):
        self.ctrl = {}
        self.result_label = {}
        control_factory = ControlFactory()
        for ctrl in controls:
            slider_name = ctrl.name
            slider_instance = control_factory.create_control(ctrl, self.update_parameter)
            slider = slider_instance.create()
            self.ctrl[slider_name] = ctrl
            self.layout_obj.addRow(slider)
            self.result_label[slider_name] = QLabel('', self)
            self.layout_obj.addRow(self.result_label[slider_name])   
            self.update_label(slider_name)

    def update_label(self, idx):
        self.result_label[idx].setText(f'{self.ctrl[idx].name} = {self.ctrl[idx].value}')

    def update_parameter(self, idx, value):
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


    def set_image_canvas(self, image_grid):
        expected_image_canvas_shape  = (len(image_grid), max([len(image_row) for image_row in image_grid]))
        if self.image_canvas is not None:
            current_canvas_shape = (len(self.image_canvas), max([len(image_row) for image_row in self.image_canvas]))
            if current_canvas_shape != expected_image_canvas_shape:
                for row_content in self.image_canvas:
                    for img_widget in row_content:
                        if img_widget is not None:
                            img_widget.setParent(None)
                self.image_canvas = None
                logging.warning("Need to fully re-initialize canvas")
        if self.image_canvas is None:
            self.image_canvas = np.empty(expected_image_canvas_shape).tolist()
            for row, image_row in enumerate(image_grid):
                for col, image_array in enumerate(image_row):
                    if image_array is None:
                        self.image_canvas[row][col] = None
                        continue
                    else:
                        self.image_canvas[row][col] = QLabel(self)
                    self.image_grid_layout.addWidget(self.image_canvas[row][col], row, col)

    def set_images(self, image_grid):
        self.set_image_canvas(image_grid)
        for row, image_row in enumerate(image_grid):
            for col, image_array in enumerate(image_row):
                if image_array is None:
                    continue
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