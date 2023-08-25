from PyQt6.QtWidgets import QApplication, QWidget, QSlider, QLabel, QFormLayout, QGridLayout, QHBoxLayout, QLineEdit, QComboBox, QCheckBox, QPushButton
from PyQt6.QtCore import Qt, QSize
from interactive_pipe.core.control import Control
from interactive_pipe.headless.pipeline import HeadlessPipeline
from functools import partial
from typing import List
import numpy as np
from PyQt6 import QtGui
from PyQt6.QtGui import QPixmap, QImage, QIcon
import sys
import logging


class InteractivePipeQT():
    def __init__(self, pipeline: HeadlessPipeline = None, controls=[], name="", inputs=None, custom_end=lambda :None, **kwargs) -> None:
        self.app = QApplication(sys.argv)
        if hasattr(pipeline, "controls"):
            controls += pipeline.controls
        self.window = MainWindow(controls=controls, name=name, pipeline=pipeline, **kwargs)
        self.custom_end = custom_end

    def run(self):
        ret = self.app.exec()
        self.custom_end()
        sys.exit(ret)



class MainWindow(QWidget):
    def __init__(self, *args, controls=[], name="", pipeline=None, fullscreen=False, width=None, center=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.pipeline = pipeline
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
        
        for ctrl in controls:
            slider_name = ctrl.name
            if ctrl._type == bool:
                slider = self.create_tick_box(ctrl, slider_name)
            elif ctrl._type == int:
                slider = self.create_int_slider(ctrl, slider_name)
            elif ctrl._type == float:
                slider = self.create_float_slider(ctrl, slider_name)
            elif ctrl._type == str:
                if ctrl.icons is not None:
                    slider = self.create_icons_bar(ctrl, slider_name)
                else:
                    slider = self.create_list_menu(ctrl, slider_name)
            self.ctrl[slider_name] = ctrl
            self.layout_obj.addRow(slider)
            self.result_label[slider_name] = QLabel('', self)
            self.layout_obj.addRow(self.result_label[slider_name])

    # @TODO: use a factory here
    def create_list_menu(self, ctrl, slider_name):
        # Create a horizontal layout to hold the dropdown menu
        hbox = QHBoxLayout()

        # Create the combo box
        combo_box = QComboBox(self)
        
        # Add items from the ctrl's value range to the combo box
        for item in ctrl.value_range:
            combo_box.addItem(item)
        
        # Set the default value for the combo box
        index = combo_box.findText(ctrl.value_default)
        if index >= 0:
            combo_box.setCurrentIndex(index)
        
        # Connect the combo box's value changed signal to some update function if needed
        combo_box.currentIndexChanged.connect(partial(self.update_parameter, slider_name))
        # Add the combo box to the horizontal layout
        hbox.addWidget(combo_box)
        return hbox

    def create_icons_bar(self, ctrl, slider_name):
        # Check if ctrl has the right type
        if ctrl._type != str or not hasattr(ctrl, 'value_range'):
            raise ValueError("Invalid control type or missing value range for icons bar creation.")
        
        # Create a horizontal layout to hold the icon buttons
        hbox = QHBoxLayout()

        # Iterate over the ctrl's value range to create buttons with icons
        for idx, icon_name in enumerate(ctrl.value_range):
            btn = QPushButton(self)
            icon_path = str(ctrl.icons[idx])  # Assuming you have a folder named 'icons' with images named after the ctrl's value range
            btn.setIcon(QIcon(icon_path))
            btn.setIconSize(QSize(64, 64))  # Example size, adjust as needed
            # btn.setCheckable(True)  # Making the button checkable if you want to show which one is currently selected

            # Connect the button's clicked signal to some update function
            btn.clicked.connect(partial(self.update_parameter, slider_name, idx))
            
            hbox.addWidget(btn)

        return hbox


    def create_tick_box(self, ctrl, slider_name):
        hbox = QHBoxLayout()

        # Create the checkbox
        checkbox = QCheckBox(slider_name, self)
        
        # Set the default state for the checkbox based on ctrl's default value
        checkbox.setChecked(ctrl.value_default)
        
        checkbox.stateChanged.connect(partial(self.update_parameter, slider_name))
        # checkbox.stateChanged.connect(partial(self.update_bool_value, slider_name, checkbox))
        
        # Add the checkbox to the horizontal layout
        hbox.addWidget(checkbox)
        return hbox

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
    

    
    def update_float_value(self, idx, line_edit, value):
        # Convert the slider's integer value to a float and update the line edit
        float_value = value / 100.0
        self.ctrl[idx].update(float_value)
        line_edit.setText(str(float_value))
        self.refresh()

    # def update_bool_value(self, idx, checkbox):
    #     checked = checkbox.isChecked()
    #     self.ctrl[idx].update(checked)
    #     self.result_label[idx].setText(f'{idx} -> Current Value: {checked} {self.ctrl[idx]}')
    #     self.refresh()

    def update_parameter(self, idx, value):
        if self.ctrl[idx]._type == str:
            self.ctrl[idx].update(self.ctrl[idx].value_range[value])
        elif self.ctrl[idx]._type == bool:
            self.ctrl[idx].update(bool(value))
        else:
            self.ctrl[idx].update(value)
        self.result_label[idx].setText(f'{idx} -> Current Value: {value} {self.ctrl[idx]}')
        self.refresh()

    # def set_image(self, image_array):
    #     h, w, c = image_array.shape
    #     bytes_per_line = c * w
    #     image = QtGui.QImage(image_array.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
    #     pixmap = QPixmap.fromImage(image)
    #     self.image_label.setPixmap(pixmap)

    def set_image_canvas(self, image_grid):
        expected_image_canvas_shape  = (len(image_grid), max([len(image_row) for image_row in image_grid]))
        if self.image_canvas is not None:
            current_canvas_shape = (len(self.image_canvas), max([len(image_row) for image_row in self.image_canvas]))
            if current_canvas_shape != expected_image_canvas_shape:
                self.image_canvas = None
                logging.warning("Need to re-initialize canvas")
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
                            print(idy, idx, out_img.shape)
                            out[idy][idx] = self.convert_image(out[idy][idx])
                    nx = len(img_row)
                else:
                    out[idy] = [self.convert_image(out[idy])]
            logging.info(f"{ny} x {nx} figures")
            self.set_images(out)