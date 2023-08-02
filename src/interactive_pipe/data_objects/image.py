import numpy as np
from pathlib import Path
import cv2
# TODO: can we get rid of cv2? use lighter PIL instead

class Image:
    def __init__(self, img) -> None:
        self.img = img

    def save(self, path):
        self.save_image(self.img, path)

    @staticmethod
    def save_image(img, path: Path, precision=8):
        amplitude = 2**precision-1
        out = np.round(img*amplitude).clip(0,
                                           amplitude).astype(np.uint8 if precision == 8 else np.uint16)
        out = cv2.cvtColor(out, cv2.COLOR_BGR2RGB)
        cv2.imwrite(str(path), out)
