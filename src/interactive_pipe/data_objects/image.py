from interactive_pipe.data_objects.data import Data
import numpy as np
from pathlib import Path
import logging

image_backends = []

IMAGE_BACKEND_PILLOW = "pillow"
IMAGE_BACKEND_OPENCV = "opencv"
IMAGE_BACKENDS = [IMAGE_BACKEND_PILLOW, IMAGE_BACKEND_OPENCV]

try:
    import cv2

    image_backends.append(IMAGE_BACKEND_OPENCV)
except ImportError:
    logging.info("cv2 is not available")

try:
    from PIL import Image as PilImage

    image_backends.append(IMAGE_BACKEND_PILLOW)
except ImportError:
    logging.info("PIL is not available")
if len(image_backends) == 0:
    raise RuntimeError("No image backends available. Please install either cv2 or PIL")

try:
    import matplotlib.pyplot as plt
except ImportError:
    logging.info("matplotlib is not available, won't be able to show images")


class Image(Data):
    def __init__(self, data, title="") -> None:
        super().__init__(data)
        self.title = title
        self.path = None

    def _set_file_extensions(self):
        self.file_extensions = [".png", ".jpg", ".tif"]

    def _save(self, path: Path, backend=None):
        if path is None:
            raise ValueError("Save requires a path")
        if self.title is not None:
            self.path = self.append_with_stem(path, self.title)
        else:
            self.path = path
        self.save_image(self.data, self.path, backend=backend)

    def _load(self, path: Path, backend=None, title=None) -> np.ndarray:
        if title is not None:
            self.title = title
        self.path = path
        return self.load_image(path, backend=backend)

    @staticmethod
    def save_image(data, path: Path, precision=8, backend=None):
        if backend is None:
            backend = IMAGE_BACKEND_PILLOW
        if backend not in IMAGE_BACKENDS:
            raise ValueError(f"backend must be one of {IMAGE_BACKENDS}, got {backend}")
        if backend == IMAGE_BACKEND_OPENCV:
            Image.save_image_cv2(data, path, precision)
        if backend == IMAGE_BACKEND_PILLOW:
            Image.save_image_PIL(data, path, precision)

    @staticmethod
    def rescale_dynamic(data, precision=8):
        if len(data.shape) == 2:
            # Black & white image
            data = np.expand_dims(data, axis=-1)  # add channel dimension
            data = np.repeat(data, 3, axis=-1)  # repeat for RGB
        amplitude = 2**precision - 1
        return np.round(data * amplitude).clip(0, amplitude)

    @staticmethod
    def normalize_dynamic(img, precision=8):
        return img / (2.0**precision - 1)  # scale image data to [0, 1]

    @staticmethod
    def save_image_cv2(data, path: Path, precision=8):
        if not isinstance(path, Path):
            raise TypeError(f"path must be a Path object, got {type(path)}")
        out = Image.rescale_dynamic(data, precision=precision)
        out = out.astype(np.uint8 if precision == 8 else np.uint16)
        out = cv2.cvtColor(out, cv2.COLOR_BGR2RGB)
        cv2.imwrite(str(path), out)

    @staticmethod
    def save_image_PIL(data, path: Path, precision=8):
        if precision != 8:
            raise ValueError(f"PIL backend requires precision=8, got {precision}")
        if not isinstance(path, Path):
            raise TypeError(f"path must be a Path object, got {type(path)}")
        out = Image.rescale_dynamic(data, precision=precision)
        out = out.astype(np.uint8)  # PIL requires image data in uint8 format
        out = PilImage.fromarray(out, "RGB")
        out.save(str(path))

    @staticmethod
    def load_image_cv2(path: Path, precision=8) -> np.ndarray:
        img = cv2.imread(str(path))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return Image.normalize_dynamic(img, precision=precision)

    @staticmethod
    def load_image_PIL(path: Path, precision=8) -> np.ndarray:
        img = PilImage.open(path)
        return Image.normalize_dynamic(np.array(img), precision=precision)

    @staticmethod
    def load_image(path: Path, precision=8, backend=None) -> np.ndarray:
        if backend is None:
            backend = IMAGE_BACKEND_PILLOW
        if backend not in IMAGE_BACKENDS:
            raise ValueError(f"backend must be one of {IMAGE_BACKENDS}, got {backend}")
        if backend == IMAGE_BACKEND_OPENCV:
            return Image.load_image_cv2(path)
        if backend == IMAGE_BACKEND_PILLOW:
            return Image.load_image_PIL(path, precision)

    def show(self):
        plt.figure()
        plt.imshow(self.data)
        ttl = (f"{self.title} -" if self.title else "") + f"{self.data.shape}"
        plt.title(ttl)
        plt.show()
