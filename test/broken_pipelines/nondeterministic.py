"""Symptom: the grain changes pattern every time any slider is moved, even 'contrast'."""

import numpy as np

from interactive_pipe import interactive, interactive_pipeline

rng = np.random.default_rng(0)


@interactive(grain=(0.05, [0.0, 0.2]))
def add_grain(img, grain=0.05):
    return img + grain * rng.normal(size=img.shape)


@interactive(contrast=(1.0, [0.5, 2.0]))
def adjust(img, contrast=1.0):
    return np.clip(0.5 + contrast * (img - 0.5), 0, 1)


@interactive_pipeline(gui="auto", cache=False)
def pipe(img):
    grainy = add_grain(img)
    adjusted = adjust(grainy)
    return adjusted


if __name__ == "__main__":
    pipe(np.full((32, 32), 0.5))
