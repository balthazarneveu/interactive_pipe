from PyQt6.QtWidgets import QApplication, QWidget, QSlider, QLabel, QFormLayout, QGridLayout, QHBoxLayout, QLineEdit
from PyQt6.QtCore import Qt
from interactive_pipe.core.control import Control
from interactive_pipe.headless.pipeline import HeadlessPipeline
from functools import partial
from typing import List
import numpy as np
from PyQt6 import QtGui
from PyQt6.QtGui import QPixmap, QImage
import sys



class InteractivePipeQT():
    def __init__(self, pipeline: HeadlessPipeline = None, controls=[], name="", inputs=None) -> None:
        self.app = QApplication(sys.argv)
        if hasattr(pipeline, "controls"):
            controls += pipeline.controls
        self.window = MainWindow(controls=controls, name=name, pipeline=pipeline)

    def run(self):
        sys.exit(self.app.exec())



class MainWindow(QWidget):
    def __init__(self, *args, controls=[], name="", pipeline=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.pipeline = pipeline
        self.setWindowTitle(name)
        self.setMinimumWidth(1000)
        self.layout_obj = QFormLayout()
        self.setLayout(self.layout_obj)
        if not isinstance(pipeline.outputs[0], list):
            pipeline.outputs = [pipeline.outputs]
        self.image_grid_layout = QGridLayout(self)
        self.layout_obj.addRow(self.image_grid_layout)
        
        self.init_sliders(controls)
        self.refresh()
        self.show()


    def create_float_slider(self, ctrl, slider_name):
        # Create a horizontal layout to hold the slider and line edit
        hbox = QHBoxLayout()

        # Create the slider with integer range and step size
        slider = QSlider(Qt.Orientation.Horizontal, self)
        slider.setRange(int(ctrl.value_range[0] * 100), int(ctrl.value_range[1] * 100))
        slider.setValue(int(ctrl.value_default * 100))
        slider.setSingleStep(5)
        slider.setPageStep(10)
        slider.setTickPosition(QSlider.TickPosition.TicksAbove)

        # Create a line edit to display the float value
        line_edit = QLineEdit(self)
        line_edit.setReadOnly(True)
        line_edit.setText(str(ctrl.value_default))

        # Connect the slider's value changed signal to update the line edit
        slider.valueChanged.connect(partial(self.update_float_value, slider_name, line_edit))

        # Add the slider and line edit to the horizontal layout
        hbox.addWidget(slider)
        hbox.addWidget(line_edit)
        return hbox
    
    def create_int_slider(self, ctrl, slider_name):
        slider = QSlider(Qt.Orientation.Horizontal, self)
        slider.setRange(ctrl.value_range[0], ctrl.value_range[1])
        slider.setValue(ctrl.value_default)
        slider.setSingleStep(5)
        slider.setPageStep(10)
        slider.setTickPosition(QSlider.TickPosition.TicksAbove)
        slider.valueChanged.connect(partial(self.update_parameter, slider_name))
        return slider
    
    def init_sliders(self, controls: List[Control]):
        self.ctrl = {}
        self.result_label = {}
        for ctrl in controls:
            slider_name=  f"slider {ctrl.name}"
            if ctrl._type == int:
                slider = self.create_int_slider(ctrl, slider_name)
            elif ctrl._type == float:
                slider = self.create_float_slider(ctrl, slider_name)
            self.ctrl[slider_name] = ctrl
            self.layout_obj.addRow(slider)
            self.result_label[slider_name] = QLabel('', self)
            self.layout_obj.addRow(self.result_label[slider_name])
    
    def update_float_value(self, idx, line_edit, value):
        # Convert the slider's integer value to a float and update the line edit
        float_value = value / 100.0
        self.ctrl[idx].update(float_value)
        line_edit.setText(str(float_value))
        self.refresh()

    def update_parameter(self, idx, value):
        self.ctrl[idx].update(value)
        self.result_label[idx].setText(f'{idx} -> Current Value: {value} {self.ctrl[idx]}')
        self.refresh()

    def set_image(self, image_array):
        h, w, c = image_array.shape
        bytes_per_line = c * w
        image = QtGui.QImage(image_array.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(image)
        self.image_label.setPixmap(pixmap)
    
    def set_images(self, image_grid):
        for row, image_row in enumerate(image_grid):
            for col, image_array in enumerate(image_row):
                if image_array is None:
                    continue
                h, w, c = image_array.shape
                bytes_per_line = c * w
                image = QImage(image_array.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                pixmap = QPixmap.fromImage(image)
                label = QLabel(self)
                label.setPixmap(pixmap)
                self.image_grid_layout.addWidget(label, row, col)

    @staticmethod
    def convert_image(out_im):
        return (out_im.clip(0., 1.)  * 255).astype(np.uint8)

    def refresh(self):
        if self.pipeline is not None:
            out = self.pipeline.run()
            for idy, img_row in enumerate(out):
                if isinstance(img_row, list):
                    for idx, out_img in enumerate(img_row):
                        if out[idy][idx] is not None:
                            out[idy][idx] = self.convert_image(out[idy][idx])
                else:
                    out[idy] = self.convert_image(out[idy])
            self.set_images(out)