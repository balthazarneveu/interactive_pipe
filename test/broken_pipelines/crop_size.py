"""Symptom: the zoomed view jumps by one pixel and its size changes as 'zoom' moves."""

import numpy as np

from interactive_pipe import interactive, interactive_pipeline


@interactive(zoom=(2.0, [1.0, 4.0]))
def center_crop(img, zoom=2.0):
    h, w = img.shape[:2]
    half_h, half_w = int(h / zoom / 2), int(w / zoom / 2)
    return img[h // 2 - half_h : h // 2 + half_h + (int(zoom * 10) % 2), w // 2 - half_w : w // 2 + half_w]


@interactive()
def upscale(crop):
    return np.repeat(np.repeat(crop, 2, axis=0), 2, axis=1)


@interactive_pipeline(gui="auto")
def pipe(img):
    crop = center_crop(img)
    zoomed = upscale(crop)
    return img, zoomed


if __name__ == "__main__":
    yy, xx = np.mgrid[0:60, 0:80]
    pipe(((xx // 8 + yy // 8) % 2).astype(float))
