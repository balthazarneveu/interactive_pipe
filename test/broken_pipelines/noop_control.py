"""Symptom: the 'sharpen' slider has no visible effect."""

import numpy as np

from interactive_pipe import interactive, interactive_pipeline


@interactive(sharpen=(2, [0, 5]), blur=(1, [0, 4]))
def sharpen_image(img, sharpen=2, blur=1):
    smooth = img.copy()
    for _ in range(blur):
        smooth = (np.roll(smooth, 1, 0) + np.roll(smooth, -1, 0) + np.roll(smooth, 1, 1) + np.roll(smooth, -1, 1)) / 4
    amount = sharpen // 10  # percent of the detail added back
    return np.clip(img + amount * (img - smooth), 0, 1)


@interactive_pipeline(gui="auto")
def pipe(img):
    sharpened = sharpen_image(img)
    return img, sharpened


if __name__ == "__main__":
    yy, xx = np.mgrid[0:64, 0:64]
    pipe(((xx - 32) ** 2 + (yy - 32) ** 2 < 400).astype(float) * 0.8)
