import argparse
import logging
from pathlib import Path
from typing import List

import numpy as np

from interactive_pipe import Panel, interactive, interactive_pipeline, layout
from interactive_pipe.data_objects.image import Image

TORCH_AVAILABLE = True
try:
    import torch
except ImportError:

    class DummyTorch:
        def no_grad(self):
            pass

        def Tensor(self, *args, **kwargs):
            return None

    torch = DummyTorch()
    TORCH_AVAILABLE = False

# Utilities functions - not anything to do with interactive pipe
# --------------------------------------------------------------------------------------------


def np_to_tensor(img: np.ndarray) -> torch.Tensor:
    if not TORCH_AVAILABLE:
        return img
    return torch.tensor(img).permute(2, 0, 1).float()


def tensor_to_np(tensor: torch.Tensor) -> np.ndarray:
    if not TORCH_AVAILABLE:
        return tensor
    return tensor.permute(1, 2, 0).contiguous().cpu().numpy()


def get_paths(img_folder: Path = Path(__file__).parent / "images"):
    img_list = sorted(list(img_folder.glob("*.png")))
    return img_list


# Interactive Filters = small legos!
# --------------------------------------------------------------------------------------------
def img_selector(img_list: List[Path], index: int = 0) -> np.ndarray:
    """Select an image from the list - sets image title"""
    img = Image.load_image(str(img_list[index]))
    # Please note the "image" key to set the title
    title = f"Image {index + 1:d}/{len(img_list)} {img_list[index].stem}"
    layout.style("image", title=title)
    return img


def blur_image(img: np.ndarray, half_blur_size=1, gpu=False) -> np.ndarray:
    blur_size = half_blur_size * 2 + 1
    if TORCH_AVAILABLE:
        with torch.no_grad():
            img_tensor = np_to_tensor(img)
            blur_conv = torch.nn.Conv2d(3, 3, blur_size, groups=3, padding=blur_size // 2, bias=False)
            blur_conv.weight.data.fill_(1.0 / (blur_size**2))
            if gpu:
                blur_conv = blur_conv.cuda()
                img_tensor = img_tensor.cuda()
            blurred_image = blur_conv(img_tensor)
            blurred_image = tensor_to_np(blurred_image)
    else:
        blurred_image = img
        logging.warning("Torch is not available, skipping blur.")
    return blurred_image


def threshold(img: np.ndarray, threshold: float = 0.5) -> np.ndarray:
    layout.style("thresholded_image", title=f"{threshold=:.2%}")
    return 1.0 * (img > threshold).max(axis=-1)


# Interactive Pipeline = Plug all legos together
# --------------------------------------------------------------------------------------------
def image_pipeline(img_list: List[Path]):
    image = img_selector(img_list)
    processed_image = blur_image(image)
    thresholded_image = threshold(processed_image)
    return [
        image,
        processed_image,
        thresholded_image,
    ]  # This is to get 3 images in a row
    # return [[image, processed_image], [thresholded_image, None]]  # This is to get a 2x2 grid


# Let's make the pipeline interactive!
# 4 possibilities: qt, gradio, mpl (matplotlib) or nb (jupyter notebook)
# --------------------------------------------------------------------------------------------


if __name__ == "__main__":
    img_list = get_paths()
    parser = argparse.ArgumentParser(description="Multi-image demo with backend selection")
    parser.add_argument(
        "-b",
        "--backend",
        type=str,
        choices=["qt", "gradio", "mpl", "nb", "dpg"],
        default="qt",
        help="Backend to use: qt, gradio, mpl, nb, or dpg (default: qt)",
    )
    parser.add_argument(
        "-p",
        "--panel",
        type=str,
        choices=["left", "right", "top", "bottom"],
        default="bottom",
        help="Panel to use: left, right, top, or bottom (default: bottom)",
    )
    args = parser.parse_args()
    blur_panel = Panel("Blurring", position=args.panel)

    # Decorate image selector - similar to @interactive
    interactive(index=(0, [0, len(img_list) - 1], "image selector", "choice"))(  # from 0 to the number of images
        img_selector
    )
    interactive(
        half_blur_size=(0, [0, 7], "blur size", blur_panel),
        gpu=(False, "gpu", blur_panel) if TORCH_AVAILABLE else None,
    )(blur_image)
    interactive(threshold=(0.5, [0.0, 1.0], "threshold", blur_panel))(threshold)
    interactive_pipeline(
        gui=args.backend,
        cache=False,
        name="Demo interactive",
        size=(10, 10) if args.backend == "nb" else None,
    )(image_pipeline)(img_list)
