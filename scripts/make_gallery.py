"""Regenerate the gallery images of docs/gallery.md from demo/gallery/*.py.

    PYTHONPATH=src MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen python scripts/make_gallery.py

One snapshot per example (docs/images/gallery/<example>.png) and a few sweeps
(<example>_sweep.png). PNGs are palette-quantised to stay small (~150 kB).
"""

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GALLERY = ROOT / "demo" / "gallery"
OUT = ROOT / "docs" / "images" / "gallery"

#: example -> (input factory or None, snapshot overrides, sweep arguments or None)
EXAMPLES = {
    "camera_isp": ("make_scene", {}, None),
    "frequency_filtering": ("make_image", {}, None),
    "signal_filtering": (None, {"kind": "IIR"}, None),
    "blob_detection": ("make_image", {}, dict(threshold=[0.2, 0.3], min_area=[1, 20], output="overlay")),
    "optimizer_trace": (None, {}, dict(optimizer=["gd", "momentum", "nesterov", "adam"], output="trajectory")),
    "lens_calibration": (None, {"k1": -0.15}, None),
    "pid_control": (None, {}, dict(kd=[0.0, 0.15, 0.4], u_max=[20.0, 2.0], output="response")),
    "reaction_diffusion": (None, {"t": 4.0}, None),
}


def load(name):
    """The example's namespace, without running its __main__ block."""
    return runpy.run_path(str(GALLERY / f"{name}.py"), run_name=f"gallery_{name}")


def compress(path, max_bytes=150_000):
    """Palette PNG: the widest size (<= 1200 px) and most colours that fit max_bytes."""
    from PIL import Image

    original = Image.open(path).convert("RGB")
    for width in (1200, 1000, 800, 640):
        img = original
        if img.width > width:
            img = img.resize((width, round(img.height * width / img.width)), Image.Resampling.LANCZOS)
        for colors in (256, 128):
            img.quantize(colors, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE).save(path, optimize=True)
            if path.stat().st_size <= max_bytes:
                return


def render(name, out_dir=OUT, sweeps=True):
    """Write the example's snapshot (and sweep); return the paths written."""
    factory, overrides, sweep = EXAMPLES[name]
    namespace = load(name)
    pipe = namespace[name]
    inputs = (namespace[factory](),) if factory else ()
    out_dir.mkdir(parents=True, exist_ok=True)
    written = [out_dir / f"{name}.png"]
    pipe.snapshot(str(written[0]), *inputs, **overrides)
    if sweeps and sweep:
        written.append(out_dir / f"{name}_sweep.png")
        pipe.sweep(str(written[-1]), *inputs, **{**overrides, **sweep})
    for path in written:
        compress(path)
    return written


if __name__ == "__main__":
    for example in sys.argv[1:] or EXAMPLES:
        for path in render(example):
            print(f"{path.relative_to(ROOT)}  {path.stat().st_size // 1024} kB")
