from interactive_pipe import Control, interactive_pipeline, interactive
import numpy as np


@interactive(
    # 1. is the default value, [0.5, 2.] is the range
    coeff=Control(1., [0.5, 2.], name="exposure"),
    # 0. is the default value, [-0.2, 0.2] is the slider range
    bias=Control(0., [-0.2, 0.2], name="offset expo")
)
def exposure(img, coeff=1., bias=0):
    '''Applies a multiplication by coeff & adds a constant bias to the image'''
    mad = img*coeff + bias
    return mad


@interactive(
    # booleans will allow adding a tickbox
    bnw=Control(True, name="Black and White")
)
def black_and_white(img, bnw=True):
    '''Averages the 3 color channels (Black & White) if bnw=True
    '''
    return np.repeat(np.expand_dims(np.average(img, axis=-1), -1), img.shape[-1], axis=-1) if bnw else img


@interactive(
    blend_coeff=Control(0.5, [0., 1.], name="blend coefficient"),
)
def blend(img0, img1, blend_coeff=0.):
    # please note that blend_coeff=0. will be replaced by the default 0.5 Control value
    '''Blends between two image. 
    - when blend_coeff=0 -> image 0  [slider to the left ] 
    - when blend_coeff=1 -> image 1   [slider to the right] 
    '''
    blended = (1-blend_coeff)*img0 + blend_coeff*img1
    return blended


@interactive_pipeline(gui="qt")
def sample_pipeline(input_image):
    exposed = exposure(input_image)
    bnw_image = black_and_white(input_image)
    blended = blend(exposed, bnw_image)
    return exposed, blended, bnw_image


if __name__ == '__main__':
    input_image = np.array([0., 0.5, 0.8])*np.ones((256, 512, 3))
    sample_pipeline(input_image)
