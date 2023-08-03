import numpy as np
from pathlib import Path
from typing import Any, Optional
import cv2

from data_objects.data import Data
# TODO: can we get rid of cv2? use lighter PIL instead




    
class Image(Data):
    def __init__(self, data, title="") -> None:
        super().__init__(data)
        self.title=title
    def _set_file_extensions(self):
        self.file_extensions = [".png", ".jpg", ".tif"]
    def _save(self, path: Path):
        self.save_image(self.data, path.with_stem(self.title))
    @staticmethod
    def save_image(data, path: Path, precision=8):
        assert isinstance(path, Path)
        amplitude = 2**precision-1
        out = np.round(data*amplitude).clip(0,
                                            amplitude).astype(np.uint8 if precision == 8 else np.uint16)
        out = cv2.cvtColor(out, cv2.COLOR_BGR2RGB)
        cv2.imwrite(str(path), out)
