from interactive_pipe import interactive_pipeline, interactive
import numpy as np

@interactive()
def exposure(img, coeff = (1., [0.5, 2.], "exposure"), bias=(0., [-0.2, 0.2])):
    '''Applies a multiplication by coeff & adds a constant bias to the image'''
    # In the GUI, the coeff will be labelled as "exposure". 
    # As the default tuple provided to bias does not end up with a string, 
    # the widget label will be "bias", simply named after the keyword arg. 
    return img*coeff + bias


@interactive()
def black_and_white(img, bnw=(True, "black and white")):
    '''Averages the 3 color channels (Black & White) if bnw=True
    '''
    # Special mention for booleans: using a tuple like (True,) allows creating the tick box.
    return np.repeat(np.expand_dims(np.average(img, axis=-1), -1), img.shape[-1], axis=-1) if bnw else img

@interactive()
def blend(img0, img1, blend_coeff=([0., 1.])):
    '''Blends between two image. 
    - when blend_coeff=0 -> image 0  [slider to the left ] 
    - when blend_coeff=1 -> image 1   [slider to the right] 
    '''
    return  (1-blend_coeff)*img0+ blend_coeff*img1

@interactive_pipeline(gui="qt", size="maximum")
def sample_pipeline(input_image):
    exposed = exposure(input_image)
    bnw_image = black_and_white(input_image)
    blended  = blend(exposed, bnw_image)
    return exposed, blended, bnw_image

if __name__ == '__main__':
    input_image = np.array([0., 0.5, 0.8])*np.ones((256, 512, 3))
    sample_pipeline(input_image)
