"""Symptom: the 'gain' slider moves but the image never gets brighter."""

import numpy as np

from interactive_pipe import interactive, interactive_pipeline


@interactive(gain=(1.0, [0.0, 3.0]))
def enhance(img, **kwargs):
    return np.clip(img * kwargs.get("strength", 1.0), 0, 1)


@interactive_pipeline(gui="auto")
def pipe(img):
    enhanced = enhance(img)
    return img, enhanced


if __name__ == "__main__":
    pipe(np.linspace(0, 0.5, 64 * 64 * 3).reshape(64, 64, 3))
