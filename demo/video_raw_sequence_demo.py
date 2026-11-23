"""
Demo: a custom file format and per-frame metadata (a burst of RAW frames).

Cameras write a sequence of RAW files (DNG...) where each frame carries its
own metadata: exposure time, ISO, white balance. This demo writes such a
burst in a made-up format (``.craw``: a 10-bit Bayer mosaic, its metadata
and a small developed preview, like the JPEG a camera embeds in its RAW
files, in a numpy archive) with an auto-exposure that hunts, so the
brightness flickers from frame to frame.

``Video(folder, loader=read_craw)`` reads the burst: the loader gets a path
and returns ``(mosaic, metadata)``. The pipeline function stays written for
one frame; the filters read the metadata of the frame on screen with
``context["timeline"].metadata`` to subtract the black level, compensate the
exposure (the flicker goes away) and apply the white balance of each shot.
``thumbnail_loader=read_craw_preview`` reads only the embedded preview for the
film strip, so the thumbnails never decode the mosaics (without one,
``preview=`` turns decoded frames into thumbnails). The window decodes the
next ``preload`` frames in the background while you watch: a band on the
ruler shows them.

For real DNG files, the loader is a few lines of ``rawpy``::

    def read_dng(path):
        with rawpy.imread(str(path)) as raw:
            return raw.raw_image_visible.astype(np.float32), {"wb": raw.camera_whitebalance}

Run it::

    python demo/video_raw_sequence_demo.py
    python demo/video_raw_sequence_demo.py --timeline collapsible
    python demo/video_raw_sequence_demo.py --slow --preload 24   # a slow disk / decoder
"""

import argparse
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np

from interactive_pipe import Video, context, interactive, interactive_pipeline, layout

BLACK_LEVEL = 64
WHITE_LEVEL = 1023


# ---------------------------------------------------------------- the custom format
def write_craw(path: Path, mosaic: np.ndarray, **metadata: Any) -> None:
    with open(path, "wb") as file:  # a file object: numpy keeps the .craw suffix
        np.savez(file, mosaic=mosaic, **metadata)


def read_craw_preview(path: Path) -> np.ndarray:
    """``Video`` thumbnail loader: the embedded preview only (an npz archive reads one array)."""
    with np.load(path) as data:
        return data["preview"]


def read_craw(path: Path) -> Tuple[np.ndarray, Dict[str, Any]]:
    """``Video`` loader: path -> (Bayer mosaic as float32, metadata dict)."""
    with np.load(path) as data:
        metadata = {
            "exposure_ms": float(data["exposure_ms"]),
            "iso": int(data["iso"]),
            "wb_gains": tuple(float(g) for g in data["wb_gains"]),
            "black_level": int(data["black_level"]),
            "white_level": int(data["white_level"]),
        }
        return data["mosaic"].astype(np.float32), metadata


def simulate_burst(folder: Path, n_frames: int = 48, size: Tuple[int, int] = (240, 320), seed: int = 0) -> Path:
    """RGGB mosaics of a moving scene, shot with a hunting auto-exposure and a drifting white balance."""
    rng = np.random.default_rng(seed)
    height, width = size
    yy, xx = np.mgrid[:height, :width] / np.array([height, width])[:, None, None]
    exposure = 10.0
    for k in range(n_frames):
        # the scene, in linear light: a blue sky, green hills, a sun crossing the sky
        cx, cy = 0.15 + 0.7 * k / n_frames, 0.3 + 0.08 * np.sin(k / 6)
        sky = np.stack([0.18 + 0.25 * yy, 0.3 + 0.25 * yy, 0.65 - 0.1 * yy], axis=-1)
        hills = (yy > 0.68 + 0.06 * np.sin(9 * xx + 1.0))[..., None]
        ground = np.stack([0.12 + 0.05 * xx, 0.3 - 0.1 * yy, 0.08 + 0 * xx], axis=-1)
        sun = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / 0.003)[..., None] * (1 - hills)
        scene = np.where(hills, ground, sky) + sun * np.array([2.2, 1.8, 1.0])
        exposure = float(np.clip(exposure * np.exp(rng.normal(0.0, 0.25)), 4.0, 25.0))  # auto-exposure hunting
        iso = int(rng.choice([100, 200, 400]))
        illuminant = np.array([1.0 + 0.1 * np.sin(k / 9), 1.0, 0.9 - 0.1 * np.sin(k / 9)])
        signal = scene * illuminant * (exposure / 10.0) * (iso / 200.0) * 0.5
        mosaic = np.empty((height, width), np.float32)
        mosaic[0::2, 0::2] = signal[0::2, 0::2, 0]  # R
        mosaic[0::2, 1::2] = signal[0::2, 1::2, 1]  # G
        mosaic[1::2, 0::2] = signal[1::2, 0::2, 1]  # G
        mosaic[1::2, 1::2] = signal[1::2, 1::2, 2]  # B
        mosaic += rng.normal(0.0, 0.004 * iso / 100, mosaic.shape)
        digital = np.clip(BLACK_LEVEL + mosaic * (WHITE_LEVEL - BLACK_LEVEL), 0, WHITE_LEVEL).astype(np.uint16)
        # what the camera shows on its screen: developed, 8 bits, a quarter of the resolution
        preview = (np.clip(signal[::4, ::4] / illuminant, 0.0, 1.0) ** (1 / 2.2) * 255).astype(np.uint8)
        write_craw(
            folder / f"burst_{k:03d}.craw",
            digital,
            preview=preview,
            exposure_ms=exposure,
            iso=iso,
            wb_gains=1.0 / illuminant,
            black_level=BLACK_LEVEL,
            white_level=WHITE_LEVEL,
        )
    return folder


# ---------------------------------------------------------------- the pipeline (one frame)
@interactive(compensate=(True, "exposure compensation"))
def normalize(mosaic: np.ndarray, compensate: bool = True) -> np.ndarray:
    """Black level to 0, white level to 1; scaled to a 10 ms ISO 200 exposure when compensating."""
    meta = context["timeline"].metadata
    raw = (mosaic - meta["black_level"]) / (meta["white_level"] - meta["black_level"])
    if compensate:
        raw = raw / ((meta["exposure_ms"] / 10.0) * (meta["iso"] / 200.0))
    layout.style("raw", title=f"ISO {meta['iso']} · {meta['exposure_ms']:.1f} ms · {Path(meta['path']).name}")
    return raw


@interactive()
def demosaic(raw: np.ndarray) -> np.ndarray:
    """RGGB to half-resolution RGB (each 2x2 block becomes a pixel)."""
    green = (raw[0::2, 1::2] + raw[1::2, 0::2]) / 2
    return np.stack([raw[0::2, 0::2], green, raw[1::2, 1::2]], axis=-1)


@interactive(white_balance=("as shot", ["as shot", "none"]), brightness=(1.0, [0.2, 3.0]))
def develop(rgb: np.ndarray, white_balance: str = "as shot", brightness: float = 1.0) -> np.ndarray:
    gains = np.array(context["timeline"].metadata["wb_gains"]) if white_balance == "as shot" else np.ones(3)
    linear = np.clip(rgb * gains * brightness, 0.0, 1.0)
    return linear ** (1 / 2.2)  # display gamma


def develop_raw(mosaic: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    raw = normalize(mosaic)
    rgb = demosaic(raw)
    developed = develop(rgb)
    return raw, developed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAW burst in a custom format, with per-frame metadata")
    parser.add_argument("-b", "--backend", choices=["qt", "dpg", "gradio", "mpl"], default="qt")
    parser.add_argument("--timeline", choices=["shown", "collapsible", "collapsed", "hidden"], default="shown")
    parser.add_argument("--preload", type=int, default=8, help="frames decoded ahead of the playhead")
    parser.add_argument("--slow", action="store_true", help="simulate a slow decoder (80 ms per frame)")
    args = parser.parse_args()
    folder = simulate_burst(Path(tempfile.mkdtemp(prefix="raw_burst_")))

    def loader(path: Path) -> Tuple[np.ndarray, Dict[str, Any]]:
        if args.slow:
            time.sleep(0.08)
        return read_craw(path)

    burst = Video(
        folder,
        fps=12,
        loader=loader,
        thumbnail_loader=read_craw_preview,  # the embedded preview: the strip never decodes the mosaics
        preload=args.preload,
        timeline=args.timeline,
    )
    interactive_pipeline(gui=args.backend, cache=True, name="RAW burst")(develop_raw)(burst)
