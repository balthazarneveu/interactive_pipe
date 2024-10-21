import numpy as np


def mad(img, coeff=2, bias=-3):
    mad_res = img * coeff + bias
    return mad_res


def blend(img1, img2, blend_coeff=0.4):
    blended = blend_coeff * img1 + (1.0 - blend_coeff) * img2
    return blended


def split_horizontally(img, line=0.5):
    split_line = int(0.5 * img.shape[-2])
    start, end = split_line - 10, split_line + 10
    return (
        img[..., :split_line, :],
        img[..., start:end, :],
        img[..., split_line:, :],
    )


def empty_output(img, empty_param=1):
    assert empty_param >= 1


def constant_image_generator(fake_param=0.5):
    assert fake_param >= 0 and fake_param <= 1
    return fake_param * np.ones((10, 10, 3))


def empty_in_empty_out(global_params={}, param_to_set=0.5):
    assert param_to_set >= 0 and param_to_set <= 1
    global_params["shared_param"] = param_to_set


def get_sample_image():
    img = 0.5 * np.ones((256, 512, 3))
    img[:, 100:, 0] *= 0.5
    img[150:, :, 2] *= 1.5
    img[:200, :, :] *= 0.5
    return img
