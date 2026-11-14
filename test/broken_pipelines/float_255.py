"""Symptom: the 'brightened' output is almost entirely white."""

import numpy as np

from interactive_pipe import interactive, interactive_pipeline


@interactive()
def load(img):
    return img.astype(np.float32)  # uint8 -> float, but the 0-255 scale is kept


@interactive(gain=(1.2, [0.5, 2.0]))
def brighten(img, gain=1.2):
    return img * gain


@interactive_pipeline(gui="auto")
def pipe(raw):
    img = load(raw)
    brightened = brighten(img)
    return brightened


if __name__ == "__main__":
    pipe((np.arange(48 * 48) % 256).reshape(48, 48).astype(np.uint8))
