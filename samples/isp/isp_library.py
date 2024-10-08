import torch
import logging


def get_rgb_indexes(phase):
    phase = phase.upper()
    r_index = phase.index("R")
    gr_index = phase.index("G")
    b_index = phase.index("B")
    logging.warning("FIX ME for other phases")
    return r_index, gr_index, b_index


def normalize_image(bayer: torch.FloatTensor, black_point: torch.FloatTensor, white_point: torch.FloatTensor):
    return (bayer - black_point)/(white_point - black_point)


def demosaick(planar_bayer: torch.FloatTensor, phase: str = "RGBG"):
    """
    R G
    B G
    """
    r_index, gr_index, b_index = get_rgb_indexes(phase)
    print(phase, r_index, gr_index, b_index)
    logging.warning("Consider implementing a real demosaicking here")
    rgb = torch.stack((
        planar_bayer[r_index, ...],
        planar_bayer[gr_index, ...],
        planar_bayer[b_index, ...])
    )
    return rgb


def apply_color_transform(
    rgb_linear: torch.FloatTensor,
    white_balance: torch.FloatTensor,
    color_matrix: torch.FloatTensor,
    inplace=False
):
    original_shape = rgb_linear.shape
    rgb = rgb_linear if inplace else rgb_linear.clone()
    if white_balance is not None:
        rgb[0, ...] *= white_balance[0]
        rgb[2, ...] *= white_balance[2]

    # If input is a (b×n×m)(b×n×m) tensor, mat2 is a (b×m×p)(b×m×p) tensor, out will be a (b×n×p)(b×n×p) tensor.
    # b= 1
    # (1,3, 3)=  * (1, 3, H*W) -> (1, 3, H*W)...
    if color_matrix is not None:
        rgb = torch.bmm(
            color_matrix.unsqueeze(0),
            rgb.view(1, rgb.shape[0], rgb.shape[-1]*rgb.shape[-2])
        )
    rgb = rgb.view(*original_shape)
    return rgb
