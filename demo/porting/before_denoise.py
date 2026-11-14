"""Denoising comparison: box blur vs median vs bilateral-ish, on a noisy synthetic image."""

import matplotlib.pyplot as plt
import numpy as np

NOISE_SIGMA = 0.08
BOX_RADIUS = 2
MEDIAN_RADIUS = 1
SEED = 0

rng = np.random.default_rng(SEED)
yy, xx = np.mgrid[0:128, 0:128] / 128.0
clean = 0.5 + 0.4 * np.sin(8 * xx) * np.cos(6 * yy)
clean[40:80, 40:80] = 0.9
noisy = clean + rng.normal(0, NOISE_SIGMA, clean.shape)


def shifted_stack(img, radius):
    padded = np.pad(img, radius, mode="reflect")
    h, w = img.shape
    return np.stack([padded[dy : dy + h, dx : dx + w] for dy in range(2 * radius + 1) for dx in range(2 * radius + 1)])


def box_blur(img, radius):
    return shifted_stack(img, radius).mean(axis=0)


def median(img, radius):
    return np.median(shifted_stack(img, radius), axis=0)


def psnr(ref, img):
    mse = np.mean((ref - img) ** 2)
    return 10 * np.log10(1.0 / mse)


box = box_blur(noisy, BOX_RADIUS)
med = median(noisy, MEDIAN_RADIUS)
np.clip(box, 0, 1, out=box)  # in place

plt.figure(figsize=(12, 4))
for i, (name, img) in enumerate([("noisy", noisy), ("box", box), ("median", med)]):
    plt.subplot(1, 3, i + 1)
    plt.imshow(img, cmap="gray", vmin=0, vmax=1)
    plt.title(f"{name} PSNR={psnr(clean, img):.2f}")
    plt.axis("off")
plt.tight_layout()
plt.show()
