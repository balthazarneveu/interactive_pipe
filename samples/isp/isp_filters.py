from pathlib import Path
import numpy as np
import torch
from interactive_pipe import interactive
from isp_library import normalize_image, demosaick, apply_color_transform
from isp_helper_filters import load_raw_buffer, visualize_tensor, bayer_crop, array_to_tensor, rawpi_prostprocess

# ----------------------------------------------------------------------------
# ISP filters declaration
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------


def normalize_raw(
    bayer: torch.FloatTensor,
    global_params={
        "raw_metadata": {"black_level": 4096., "white_level": 2**16-1},
    }
) -> torch.FloatTensor:
    raw_metadata = global_params["raw_metadata"]
    # substract blackpoint
    black_point = torch.tensor(
        raw_metadata["black_level"],
        device=bayer.device
    )
    white_level = torch.tensor(
        raw_metadata["white_level"],
        device=bayer.device
    )
    return normalize_image(bayer, black_point, white_level)

# ----------------------------------------------------------------------------


def planar_bayer_to_channels(planar_bayer: torch.FloatTensor) -> torch.FloatTensor:
    """Planar to 4 separate channels """
    return torch.pixel_unshuffle(planar_bayer, downscale_factor=2)


# ----------------------------------------------------------------------------
def demosaick_filter(planar_bayer: torch.FloatTensor,
                     global_params={}
                     #  global_params: dict ={"raw_metadata": {"raw_phase": "RGBG"}}
                     ) -> torch.FloatTensor:
    return demosaick(planar_bayer, str(global_params["raw_metadata"]["raw_phase"]))

# ----------------------------------------------------------------------------


@interactive(apply_white_balance=(True, "white balance"), apply_color_matrix=(False, "color matrix"))
def neutral_to_realistic(
    rgb_linear: torch.FloatTensor,
    apply_white_balance=True,
    apply_color_matrix=False,
    global_params={
        "raw_metadata": {
            'white_balance': [2.162109375, 1.0, 1.6845704317092896],
            'color_matrix': np.array(
                [
                    [1.6645684, -0.6500865, -0.01448185],
                    [-0.13407078,  1.4680636, -0.3339928],
                    [-0.00423043, -0.46748492,  1.4717153]
                ]
            )
        }
    }
) -> torch.FloatTensor:
    raw_metadata = global_params["raw_metadata"]
    device = rgb_linear.device
    if apply_white_balance:
        white_balance = torch.tensor(raw_metadata["white_balance"], device=device)
    else:
        white_balance = torch.ones((3,), device=device)

    if apply_color_matrix and raw_metadata["color_matrix"] is not None:
        color_matrix = torch.tensor(raw_metadata["color_matrix"], device=device)
    else:
        color_matrix = torch.eye(3, device=device)
    return apply_color_transform(rgb_linear, white_balance, color_matrix, inplace=False)

# ----------------------------------------------------------------------------


@interactive(gamma=(2.2, [1., 2.2]))
def apply_tone_curve(rgb: torch.FloatTensor, gamma: float = 2.2) -> torch.FloatTensor:
    """Gamma curve"""
    return torch.pow(rgb, 1./gamma)

# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# Define pipeline


def isp_pipeline(path: Path):
    bayer = load_raw_buffer(path)

    planar_bayer_tensor_full = array_to_tensor(bayer)
    planar_bayer_tensor_crop = bayer_crop(planar_bayer_tensor_full)
    planar_bayer_tensor = normalize_raw(planar_bayer_tensor_crop)
    bayer_tensor = planar_bayer_to_channels(planar_bayer_tensor)
    rgb_linear = demosaick_filter(bayer_tensor)
    rgb = neutral_to_realistic(rgb_linear)
    rgb = apply_tone_curve(rgb)
    rgb_viz = visualize_tensor(rgb)
    return rgb_viz


def isp_monolithic_rawpipipeline(path: Path):
    rgb_new = rawpi_prostprocess(path)
    rgb_new = bayer_crop(rgb_new)
    return rgb_new
