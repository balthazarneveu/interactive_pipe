from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.graphical.qt_gui import InteractivePipeQT
from interactive_pipe.graphical.mpl_gui import InteractivePipeMatplotlib
from interactive_pipe.graphical.nb_gui import InteractivePipeJupyter
from interactive_pipe import interactive
from interactive_pipe.data_objects.image import Image
from pathlib import Path
import torch
from typing import List
import numpy as np

# Utilities functions - not anything to do with interactive pipe
# --------------------------------------------------------------------------------------------


def np_to_tensor(img: np.ndarray) -> torch.Tensor:
    return torch.tensor(img).permute(2, 0, 1).float()


def tensor_to_np(tensor: torch.Tensor) -> np.ndarray:
    return tensor.permute(1, 2, 0).contiguous().cpu().numpy()


def get_paths(img_folder: Path = Path(__file__).parent/"images"):
    img_list = sorted(list(img_folder.glob("*.png")))
    return img_list


# Interactive Filters = small legos!
# --------------------------------------------------------------------------------------------
def img_selector(img_list: List[Path], index: int = 0, global_params={}) -> np.ndarray:
    """Select an image from the list - sets image title"""
    img = Image.load_image(str(img_list[index]))
    # Please note the "image" key to set the title
    title = f"Image {index:d}/{len(img_list)} {img_list[index].stem}"
    global_params["__output_styles"]["image"] = {"title": title}
    return img


@interactive(
    half_blur_size=(0, [0, 7]),
    gpu=(False,)
)
def blur_image(img: np.ndarray, half_blur_size=1, gpu=False, global_params={}) -> np.ndarray:
    blur_size = half_blur_size*2+1
    with torch.no_grad():
        img_tensor = np_to_tensor(img)
        blur_conv = torch.nn.Conv2d(3, 3, blur_size, groups=3, padding=blur_size//2, bias=False)
        blur_conv.weight.data.fill_(1.0 / (blur_size**2))
        if gpu:
            blur_conv = blur_conv.cuda()
            img_tensor = img_tensor.cuda()
        blurred_image = blur_conv(img_tensor)
        blurred_image = tensor_to_np(blurred_image)
    return blurred_image


@interactive(
    threshold=(0.5, [0.0, 1.0])
)
def threshold(img: np.ndarray, threshold: float = 0.5, global_params={}) -> np.ndarray:
    global_params["__output_styles"]["thresholded_image"] = {"title": f"{threshold=:.2%}"}
    return (img > threshold).max(axis=-1)


# Interactive Pipeline = Plug all legos together
# --------------------------------------------------------------------------------------------
def image_pipeline(img_list: List[Path]):
    image = img_selector(img_list)
    processed_image = blur_image(image)
    thresholded_image = threshold(processed_image)
    return [image, processed_image, thresholded_image]  # This is to get 3 images in a row
    # return [[image, processed_image], [thresholded_image, None]]  # This is to get a 2x2 grid

# Let's make the pipeline interactive!
# 3 possitiblities: qt, mpl (matplotlib) or nb (jupyter notebook)
# --------------------------------------------------------------------------------------------


def main_demo(img_list: List[Path], backend="qt"):
    # Decorate image selector - similar to @interactive
    interactive(
        index=(0, [0, len(img_list)-1])  # from 0 to the number of images
    )(img_selector)

    pipe = HeadlessPipeline.from_function(image_pipeline, cache=False)
    backend_pipeline = {
        "qt": InteractivePipeQT,
        "mpl": InteractivePipeMatplotlib,
        "nb": InteractivePipeJupyter
    }
    app = backend_pipeline[backend](
        pipeline=pipe,
        name="Demo interactive",
        size=(10, 10) if backend == "nb" else None,
    )
    app(img_list)


if __name__ == "__main__":
    img_list = get_paths()
    main_demo(img_list)
