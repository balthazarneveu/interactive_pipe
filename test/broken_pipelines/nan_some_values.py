"""Symptom: for some 'gamma' values part of the image turns black."""

import numpy as np

from interactive_pipe import interactive, interactive_pipeline


@interactive(offset=(0.0, [-0.2, 0.2]))
def black_level(img, offset=0.0):
    return img + offset


@interactive(gamma=(1.0, [0.5, 2.5]))
def tone(img, gamma=1.0):
    return img ** (1 / gamma)


@interactive()
def vignette(img):
    yy, xx = np.mgrid[0 : img.shape[0], 0 : img.shape[1]]
    r = np.hypot(yy - img.shape[0] / 2, xx - img.shape[1] / 2) / img.shape[0]
    return img * (1 - r)


@interactive_pipeline(gui="auto")
def pipe(img):
    shifted = black_level(img, offset=-0.1)
    toned = tone(shifted)
    result = vignette(toned)
    return result


if __name__ == "__main__":
    pipe(np.tile(np.linspace(0, 1, 64), (48, 1)))
