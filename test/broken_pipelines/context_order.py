"""Symptom: the overlay lags one step behind the 'level' slider (and is wrong at start-up)."""

import numpy as np

from interactive_pipe import context, interactive, interactive_pipeline


@interactive()
def annotate(img):
    level = context.get("level", 0.0)
    out = img.copy()
    out[:, : int(level * img.shape[1])] *= 0.5
    return out


@interactive(level=(0.5, [0.0, 1.0]))
def measure(img, level=0.5):
    context["level"] = level
    return img > level


@interactive_pipeline(gui="auto")
def pipe(img):
    annotated = annotate(img)
    mask = measure(img)
    return annotated, mask


if __name__ == "__main__":
    pipe(np.tile(np.linspace(0, 1, 64), (32, 1)))
