import numpy as np
def mad(img, coeff=2, bias=-3):
    mad_res = img*coeff+bias
    return [mad_res]


def blend(img1, img2, blend_coeff=0.4):
    blended = blend_coeff*img1+(1-blend_coeff)*img2
    return [blended]


def split_horizontally(img, line=0.5):
    split_line = int(0.5 * img.shape[-2])
    return [img[..., :split_line, :], img[..., split_line-10: split_line+10, :], img[..., split_line:, :]]

def get_sample_image():
    img = 0.5*np.ones((256, 512, 3))
    img[:, 100:, 0] *= 0.5
    img[150:, :, 2] *= 1.5
    img[:200, :, :] *= 0.5
    return img