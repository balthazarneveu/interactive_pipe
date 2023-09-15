import torchvision
import rawpy
from pathlib import Path
import torch
from interactive_pipe import interact, interactive
import numpy as np
import logging

# Load raw buffer, move to GPU, crop
# ---------------------------------------------------------------------------------
# ---------------------------------------------------------------------------------

# NEED TO OVERRIDE THE DEFAULT PARAMETERS WHEN USING INTERACT DECORATOR
# @interact(SAMPLE_PATH, gui="mpl", debug_normalize_bayer=(True,))
def load_raw_buffer(path: Path, global_params={}, debug_normalize_bayer=False) -> np.ndarray:
    
    with rawpy.imread(str(path)) as raw:
        white_balance = np.array(raw.camera_whitebalance)[:3]
        white_balance = white_balance/white_balance[1]
        raw_indexes = raw.raw_pattern.flatten().astype(np.uint).tolist()
        standard_phase = raw.color_desc.decode('ascii')
        color_matrix = raw.color_matrix[:3, :3]
        if color_matrix[0, 0] == 0:
            logging.warning(f"empty color matrix provided {color_matrix}")
            color_matrix = None
        raw_metadata = dict(
            white_balance = white_balance,
            color_matrix = color_matrix,
            raw_phase = "".join([standard_phase[idx] for idx in raw_indexes]),
            black_level_per_channel = np.array(raw.black_level_per_channel),
            black_level = np.average(np.array(raw.black_level_per_channel)),
            white_level = raw.white_level,
        )
        global_params["raw_metadata"] = raw_metadata
        print(raw_metadata)
        # print(type(raw_metadata["black_level_per_channel"]))
        # bayer = raw.raw_image.copy()
        bayer = raw.raw_image_visible.copy()
    if debug_normalize_bayer:
        # This is just for visualization
        bayer = bayer.astype(np.float32)/(2**16-1)
    return bayer

def rawpi_prostprocess(path: Path):
    with rawpy.imread(str(path)) as raw:
        rgb = raw.postprocess(no_auto_bright=True, output_bps=16)
    return rgb/(2.**16-1)

@interactive(device=["cpu", "cuda"])
def array_to_tensor(image: np.ndarray, device: str="cpu") -> torch.FloatTensor:
    """Returns tensor on CPU/GPU (cuda) -> channel first tensor C,H,W"""
    image_tensor = torch.tensor(image.astype(np.float32), device=device)
    if len(image_tensor.shape) == 2: # 1, H, W
        image_tensor = image_tensor.unsqueeze(0)
    return image_tensor


# ---------------------------------------------------------------------------------
# Helper to process much smaller raw imagge
@interactive(
    center_x=(0.5, [0., 1.], "cx", ["left", "right"]),
    center_y=(0.5, [0., 1.], "cy", ["up", "down"]),
    size=(6., [6., 13., 0.3], "crop size", ["+", "-"])
)
def bayer_crop(planar_bayer, center_x=0.5, center_y=0.5, size=8.):
    #size is defined in power of 2
    
    if len(planar_bayer.shape) == 2:
        offset = 0
    elif len(planar_bayer.shape) == 3:
        channel_guesser_max_size = 4 
        if planar_bayer.shape[0] <=channel_guesser_max_size: #channel first C,H,W
            offset = 0
        elif planar_bayer.shape[-1] <=channel_guesser_max_size: #channel last or numpy H,W,C
            offset = 1
    else:
        raise NameError(f"Not supported shape {planar_bayer.shape}")
    crop_size_pixels =  int(2.**(size)/2. //4 ) *4
    half_crop_h, half_crop_w = crop_size_pixels, crop_size_pixels
    h, w = planar_bayer.shape[-2-offset], planar_bayer.shape[-1-offset]
    def multiple_of_four(val):
        return int(val//4)*4
    center_x_int = multiple_of_four(half_crop_w+center_x*(h-2*half_crop_w))
    center_y_int = multiple_of_four(half_crop_h +center_y*(w-2*half_crop_h))
    start_x = max(0, center_x_int-half_crop_w)
    start_y = max(0, center_y_int-half_crop_h)
    end_x = min(start_x+2*half_crop_w, multiple_of_four(w-1))
    end_y = min(start_y+2*half_crop_h, multiple_of_four(h-1))
    start_x = max(0, end_x-2*half_crop_w)
    start_y = max(0, end_y-2*half_crop_h)
    if offset ==0:
        return planar_bayer[..., start_y:end_y, start_x:end_x]
    if offset==1:
        return planar_bayer[..., start_y:end_y, start_x:end_x, :]

# ---------------------------------------------------------------------------------
# ---------------------------------------------------------------------------------
# Move back tensors to CPU to visualize
def visualize_tensor(in_tensor: torch.FloatTensor, resize_flag=True, resize=256):
    tensor = in_tensor.clone()
    if len(tensor.shape) == 3:
        if tensor.shape[0] >3:
            logging.warning("showing the first 3 channels only")
            tensor = tensor[:3]
        if resize_flag:
            resize_operator = torchvision.transforms.Resize(
                resize,
                interpolation=torchvision.transforms.InterpolationMode.BILINEAR,
                max_size=None,
                antialias='warn'
            )
            tensor = resize_operator(tensor)
        tensor = tensor.permute(1, 2, 0) # C,H,W -> H,W,C
    tensor = tensor.contiguous()
    tensor = tensor.detach().to("cpu").numpy()
    return tensor