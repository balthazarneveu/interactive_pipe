from pathlib import Path
import numpy as np
import torch
from interactive_pipe import interactive_pipeline, interactive
from isp_library import normalize_image, demosaick, apply_color_transform
from isp_helper_filters import load_raw_buffer, visualize_tensor, bayer_crop, array_to_tensor, rawpi_prostprocess, histogram, Interp
from interactive_pipe.data_objects.curves import Curve, SingleCurve


# ----------------------------------------------------------------------------
# ISP filters declaration
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
def normalize_raw(
        bayer,
        global_params={
            "raw_metadata": {"black_level": 4096., "white_level": 2**16-1},
        }
    )-> torch.FloatTensor:
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
@interactive(
    apply_white_balance= (True, "white balance"),
    apply_color_matrix=(False, "color matrix")
)
def neutral_to_realistic(
        rgb_linear: torch.FloatTensor,
        apply_white_balance=True,
        apply_color_matrix=False,
        global_params={
            "raw_metadata": {
                'white_balance': [2.162109375, 1.0, 1.6845704317092896],
                'color_matrix': np.array(
                    [
                        [ 1.6645684 , -0.6500865 , -0.01448185],
                        [-0.13407078,  1.4680636 , -0.3339928],
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
        color_matrix =  torch.tensor(raw_metadata["color_matrix"], device=device)
    else:
        color_matrix = torch.eye(3, device=device)
    return apply_color_transform(rgb_linear, white_balance, color_matrix, inplace=False)

# ----------------------------------------------------------------------------
@interactive(gamma=(2.2, [1., 2.2]))
def apply_tone_curve(rgb: torch.FloatTensor, gamma: float=2.2) -> torch.FloatTensor:
    """Gamma curve"""
    return torch.pow(rgb, 1./gamma)

@interactive(bins=(512, [16, 4096, 64]))
def compute_histogram(rgb, bins=512):
    style="-"
    name="histo"
    luma = torch.mean(rgb, dim=(-3))
    # histo, histo_bins = torch.histogram(luma, bins=256, range=(0,1), density=True) # Not working on a GPU
    histo, histo_bins = histogram(luma, bins=bins, range=(0,1), density=True)
    return (histo, histo_bins, style, name),


def get_cumulative_histo(histo_in):
    histo, histo_bins = histo_in[:2]
    histo_cum = torch.cumsum(histo, 0)
    return (histo_cum, histo_bins, "", "cum"),


def get_equalization_tone_curve(histo_in, image):
    histo, histo_bins = histo_in[:2]
    histo_cum = torch.cumsum(histo, 0)
    
    interp = Interp([histo_bins[:-1]], histo_cum)
    tone_mapped = interp([image.view(image.shape[0]*image.shape[-2]*image.shape[-1])])
    tone_mapped = tone_mapped.view(image.shape)
    return tone_mapped

# ----------------------------------------------------------------------------
def stack_histograms(*histos) -> torch.FloatTensor:
    """Stack several histograms into a curve
    No custom legend so far!
    """
    histo_curve = Curve(
        [
            (histo_bins[:-1].detach().to("cpu").numpy(), histo.detach().to("cpu").numpy(), "-", f"{name} {index}")
            for index, (histo, histo_bins, style, name) in enumerate(histos)
        ],
        grid=True,
        title="Histogram",
        xlim=(0., 1.),
        ylim=(0., 0.01)
    )
    return histo_curve


# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
def isp_pipeline(path: Path):
    bayer = load_raw_buffer(path)
    planar_bayer_tensor_full = array_to_tensor(bayer)
    planar_bayer_tensor_crop = bayer_crop(planar_bayer_tensor_full)
    planar_bayer_tensor = normalize_raw(planar_bayer_tensor_crop)
    bayer_tensor = planar_bayer_to_channels(planar_bayer_tensor)
    rgb_linear = demosaick_filter(bayer_tensor)
    hist_raw = compute_histogram(rgb_linear) #, style="k--", name="raw")
    rgb = neutral_to_realistic(rgb_linear)
    hist_lin = compute_histogram(rgb) #, style="g-", name="linear")
    
    rgb = apply_tone_curve(rgb)
    hist = compute_histogram(rgb) #, style="b-", name="rgb gamma")
    tm = get_equalization_tone_curve(hist, rgb)
    hist_eq = compute_histogram(tm) #, style="b-", name="rgb gamma")
    
    histogram_curve = stack_histograms(hist, hist_lin, hist_raw, hist_eq)
    rgb_viz = visualize_tensor(rgb)
    tm_viz = visualize_tensor(tm)
    
    return rgb_viz, histogram_curve, tm_viz


def isp_monolithic_rawpipipeline(path: Path):
    rgb_new = rawpi_prostprocess(path)
    rgb_new = bayer_crop(rgb_new)

    return rgb_new


if __name__ == "__main__":
    SAMPLE_PATH = Path(__file__).parent/'images'/'dji_mavic_3.dng'
    # SAMPLE_PATH = Path(__file__).parent/'images'/ 'canon_5d.CR2'
    # SAMPLE_PATH = Path(__file__).parent/'images'/'sony_rx100iv.ARW'

    # isp_monolithic_rawpipipeline_gui = interactive_pipeline(gui="mpl", cache=True)(isp_monolithic_rawpipipeline)
    # isp_monolithic_rawpipipeline_gui(SAMPLE_PATH)
    isp_pipeline_gui = interactive_pipeline(gui="qt", cache=True)(isp_pipeline)
    isp_pipeline_gui(SAMPLE_PATH)

    # isp_pipeline(SAMPLE_PATH)