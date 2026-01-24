import logging
import numpy as np
from typing import List
import argparse
from pathlib import Path
from interactive_pipe.data_objects.image import Image
from interactive_pipe import interactive, interactive_pipeline

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
def img_selector(img_list: List[Path], index: int = 0, global_params={}) -> np.ndarray:
    """Select an image from the list - sets image title"""
    img = Image.load_image(str(img_list[index]))
    # Please note the "image" key to set the title
    title = f"Image {index+1:d}/{len(img_list)} {img_list[index].stem}"
    global_params["__output_styles"]["image"] = {"title": title}
    return img


@interactive(half_blur_size=(0, [0, 7]), gpu=(False,) if TORCH_AVAILABLE else None)
def blur_image(
    img: np.ndarray, half_blur_size=1, gpu=False, global_params={}
) -> np.ndarray:
    blur_size = half_blur_size * 2 + 1
    if TORCH_AVAILABLE:
        with torch.no_grad():
            img_tensor = np_to_tensor(img)
            blur_conv = torch.nn.Conv2d(
                3, 3, blur_size, groups=3, padding=blur_size // 2, bias=False
            )
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


@interactive(threshold=(0.5, [0.0, 1.0]))
def threshold(img: np.ndarray, threshold: float = 0.5, global_params={}) -> np.ndarray:
    global_params["__output_styles"]["thresholded_image"] = {
        "title": f"{threshold=:.2%}"
    }
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
    parser = argparse.ArgumentParser(
        description="Multi-image demo with backend selection"
    )
    parser.add_argument(
        "-b",
        "--backend",
        type=str,
        choices=["qt", "kivy", "gradio", "mpl", "nb"],
        default="qt",
        help="Backend to use: qt, kivy, gradio, mpl, or nb (default: qt)",
    )
    args = parser.parse_args()

    # Decorate image selector - similar to @interactive
    interactive(index=(0, [0, len(img_list) - 1]))(  # from 0 to the number of images
        img_selector
    )

    interactive_pipeline(
        gui=args.backend,
        cache=False,
        name="Demo interactive",
        size=(10, 10) if args.backend == "nb" else None,
    )(image_pipeline)(img_list)
