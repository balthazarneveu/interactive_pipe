"""Denoising comparison with sliders (port of before_denoise.py)."""

import numpy as np

from interactive_pipe import Image, interactive, interactive_pipeline


def shifted_stack(img, radius):
    padded = np.pad(img, radius, mode="reflect")
    h, w = img.shape
    return np.stack([padded[dy : dy + h, dx : dx + w] for dy in range(2 * radius + 1) for dx in range(2 * radius + 1)])


def psnr(ref, img):
    mse = np.mean((ref - img) ** 2)
    return 10 * np.log10(1.0 / mse)


@interactive(noise_sigma=(0.08, [0.0, 0.3]), seed=(0, [0, 10]))
def add_noise(clean, noise_sigma=0.08, seed=0):
    rng = np.random.default_rng(seed)  # seeded here: same noise on every run
    noisy = clean + rng.normal(0, noise_sigma, clean.shape)
    return Image(noisy, title=f"noisy PSNR={psnr(clean, noisy):.2f}")


@interactive(box_radius=(2, [1, 6]))
def box_blur(noisy, clean, box_radius=2):
    box = np.clip(shifted_stack(noisy.data, box_radius).mean(axis=0), 0, 1)
    return Image(box, title=f"box PSNR={psnr(clean, box):.2f}")


@interactive(median_radius=(1, [1, 4]))
def median(noisy, clean, median_radius=1):
    med = np.median(shifted_stack(noisy.data, median_radius), axis=0)
    return Image(med, title=f"median PSNR={psnr(clean, med):.2f}")


@interactive_pipeline(gui="auto")
def denoise(clean):
    noisy = add_noise(clean)
    box = box_blur(noisy, clean)
    med = median(noisy, clean)
    return noisy, box, med


def synthetic_image():
    yy, xx = np.mgrid[0:128, 0:128] / 128.0
    clean = 0.5 + 0.4 * np.sin(8 * xx) * np.cos(6 * yy)
    clean[40:80, 40:80] = 0.9
    return clean


if __name__ == "__main__":
    denoise(synthetic_image())
