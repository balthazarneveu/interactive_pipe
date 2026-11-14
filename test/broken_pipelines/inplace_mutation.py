"""Symptom: the app crashes when the 'threshold' slider is moved."""

import numpy as np

from interactive_pipe import interactive, interactive_pipeline


@interactive(threshold=(0.5, [0.0, 1.0]))
def mask_dark(img, threshold=0.5):
    img[img < threshold] = 0.0
    return img


@interactive_pipeline(gui="auto")
def pipe(img):
    masked = mask_dark(img)
    return img, masked


if __name__ == "__main__":
    pipe(np.linspace(0, 1, 32 * 32).reshape(32, 32))
