import sys
from PyQt6.QtCore import Qt
from interactive_pipe.core.control import Control
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.graphical.qt_gui import InteractivePipeQT
import numpy as np


def mad(img, coeff=100, bias=0.):
    mad_res = img*coeff/100.+ bias/100.
    return [mad_res]

def blend(img1, img2, blend_coeff=0.5):
    blended = blend_coeff*img1+(1-blend_coeff)*img2
    return [blended]

def sample_pipeline(img):
    exposed = mad(img)
    blended  = blend(img, exposed)
    return blended, exposed, img


def get_sample_image():
    img = 0.5*np.ones((256, 512, 3))
    img[:, 100:, 0] *= 0.5
    img[150:, :, 2] *= 1.5
    img[:200, :, :] *= 0.5
    return img

if __name__ == '__main__':
    # control_list=  [
    #     Control(50, [0, 100], name="flux %"),
    #     Control(0, [-1, 1]),
    #     Control(50, [0, 100], name="assistance %"),
    #     Control(3, [-5, 5])
    # ]

    input_image = get_sample_image()
    pip = HeadlessPipeline.from_function(sample_pipeline, inputs=[input_image, 0.8*input_image], cache=True)
    expo = Control(50, [0, 100], name="slide expo", 
                   filter_to_connect=pip.filters[0], parameter_name_to_connect="coeff")
    bias = Control(0, [-20, 20], name="bias expo")
    
    bias.connect_filter(pip.filters[0], "bias")
    blend_coeff = Control(.5, [0., 1.], name="blend", 
                   filter_to_connect=pip.filters[1], parameter_name_to_connect="blend_coeff")
    control_list = [expo, bias, blend_coeff]

    # pip.outputs = [[0, 1, 2, 0],[0, None, 2, None],]
    
    app = InteractivePipeQT(pipeline=pip, controls=control_list, name="blender")
    app.run()
